"""Windows handle-bound control used only by the explicitly invoked handoff tool."""
from __future__ import annotations

import ctypes
from ctypes import wintypes as w
import hashlib
import os
from pathlib import Path
from typing import Any

from newsresearch.common import AuditError, Json
from luna_batch_budget_run import ROOT


class WindowsWorker:
    synthetic = False

    def __init__(self, expected: Json) -> None:
        if os.name != "nt":
            raise AuditError("handoff_windows_required")
        self.expected, self.handle = expected, None
        self.kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        self.nt = ctypes.WinDLL("ntdll")
        self.kernel.OpenProcess.argtypes = [w.DWORD, w.BOOL, w.DWORD]
        self.kernel.OpenProcess.restype = w.HANDLE
        self.kernel.CloseHandle.argtypes = [w.HANDLE]
        self.kernel.GetProcessTimes.argtypes = [w.HANDLE, ctypes.POINTER(w.FILETIME), ctypes.POINTER(w.FILETIME), ctypes.POINTER(w.FILETIME), ctypes.POINTER(w.FILETIME)]
        self.kernel.QueryFullProcessImageNameW.argtypes = [w.HANDLE, w.DWORD, w.LPWSTR, ctypes.POINTER(w.DWORD)]
        self.kernel.TerminateProcess.argtypes = [w.HANDLE, w.UINT]
        self.kernel.WaitForSingleObject.argtypes = [w.HANDLE, w.DWORD]
        self.kernel.WaitForSingleObject.restype = w.DWORD
        self.nt.NtSuspendProcess.argtypes = self.nt.NtResumeProcess.argtypes = [w.HANDLE]
        self.nt.NtSuspendProcess.restype = self.nt.NtResumeProcess.restype = w.LONG
        self.nt.NtQueryInformationProcess.argtypes = [w.HANDLE, w.ULONG, w.LPVOID, w.ULONG, ctypes.POINTER(w.ULONG)]
        self.nt.NtQueryInformationProcess.restype = w.LONG
        self.handle = self.kernel.OpenProcess(0x00100000 | 0x1000 | 0x0400 | 0x0800 | 0x0001, False, expected["worker_pid"])
        if not self.handle:
            raise AuditError("handoff_worker_open_failed")

    def _created(self, handle: Any) -> int:
        creation, exit_time, kernel, user = (w.FILETIME() for _ in range(4))
        if not self.kernel.GetProcessTimes(handle, ctypes.byref(creation), ctypes.byref(exit_time), ctypes.byref(kernel), ctypes.byref(user)):
            raise AuditError("handoff_process_creation_unavailable")
        return (creation.dwHighDateTime << 32) | creation.dwLowDateTime

    def identity(self) -> Json:
        class Basic(ctypes.Structure):
            _fields_ = [("exit_status", w.LONG), ("peb", w.LPVOID), ("affinity", ctypes.c_size_t),
                ("priority", w.LONG), ("pid", ctypes.c_size_t), ("parent", ctypes.c_size_t)]
        class Unicode(ctypes.Structure):
            _fields_ = [("length", w.USHORT), ("maximum", w.USHORT), ("buffer", w.LPVOID)]
        basic, size = Basic(), w.ULONG()
        if self.nt.NtQueryInformationProcess(self.handle, 0, ctypes.byref(basic), ctypes.sizeof(basic), ctypes.byref(size)) < 0:
            raise AuditError("handoff_parent_identity_unavailable")
        created = self._created(self.handle)
        if (basic.pid != self.expected["worker_pid"] or created != self.expected["worker_created_100ns"]
                or basic.parent != self.expected["parent_pid"] or self.kernel.WaitForSingleObject(self.handle, 0) != 258):
            raise AuditError("handoff_worker_or_parent_pid_reused_or_exited")
        parent = self.kernel.OpenProcess(0x1000, False, basic.parent)
        if not parent:
            raise AuditError("handoff_expected_parent_unavailable")
        try:
            if self._created(parent) != self.expected["parent_created_100ns"]:
                raise AuditError("handoff_parent_pid_reused")
        finally:
            self.kernel.CloseHandle(parent)
        image, image_size = ctypes.create_unicode_buffer(32768), w.DWORD(32768)
        if not self.kernel.QueryFullProcessImageNameW(self.handle, 0, image, ctypes.byref(image_size)):
            raise AuditError("handoff_worker_image_unavailable")
        self.nt.NtQueryInformationProcess(self.handle, 60, None, 0, ctypes.byref(size))
        if not 1 <= size.value <= 131072:
            raise AuditError("handoff_command_line_size_invalid")
        buffer = ctypes.create_string_buffer(size.value)
        if self.nt.NtQueryInformationProcess(self.handle, 60, buffer, size, ctypes.byref(size)) < 0:
            raise AuditError("handoff_command_line_unavailable")
        line = Unicode.from_buffer(buffer)
        command = ctypes.wstring_at(line.buffer, line.length // 2)
        shell = ctypes.WinDLL("shell32", use_last_error=True)
        shell.CommandLineToArgvW.argtypes = [w.LPCWSTR, ctypes.POINTER(ctypes.c_int)]
        shell.CommandLineToArgvW.restype = ctypes.POINTER(w.LPWSTR)
        count = ctypes.c_int()
        argv = shell.CommandLineToArgvW(command, ctypes.byref(count))
        if not argv:
            raise AuditError("handoff_command_line_parse_failed")
        try:
            args = [argv[i] for i in range(count.value)]
        finally:
            self.kernel.LocalFree.argtypes = [w.LPVOID]
            self.kernel.LocalFree(argv)
        script = (ROOT / "scripts/run_luna_budget_throughput.py").resolve()
        if (Path(image.value).resolve() != Path(self.expected["worker_image"]).resolve()
                or len(args) < 4 or Path(args[1]).resolve() != script
                or args.count("--plan") != 1 or args[args.index("--plan") + 1] != self.expected["plan"]
                or hashlib.sha256(command.encode()).hexdigest() != self.expected["command_line_sha256"]):
            raise AuditError("handoff_exact_worker_script_command_required")
        return {key: self.expected[key] for key in ("worker_pid", "worker_created_100ns", "parent_pid", "parent_created_100ns", "worker_image", "command_line_sha256")}

    def suspend(self) -> None:
        if self.nt.NtSuspendProcess(self.handle) != 0:
            raise AuditError("handoff_suspend_failed")

    def resume(self) -> None:
        if self.kernel.WaitForSingleObject(self.handle, 0) == 0:
            return
        if self.nt.NtResumeProcess(self.handle) != 0:
            raise AuditError("handoff_resume_failed_manual_recovery_required")

    def terminate(self) -> None:
        if not self.kernel.TerminateProcess(self.handle, 130):
            raise AuditError("handoff_terminate_failed")
        if self.kernel.WaitForSingleObject(self.handle, 30000) != 0:
            raise AuditError("handoff_exact_worker_exit_not_confirmed")

    def close(self) -> None:
        if self.handle:
            self.kernel.CloseHandle(self.handle)
            self.handle = None
