@timer
def cluster(records):
    # Set Global Variables # ToDO Find "pythonic" way of doing this
    global label_tracker
    global is_cluster
    global distance_matrix
    global embeds

    global unique_article_id
    global unique_cluster_id
    global cluster_count
    global batch_times
    global processed_pool_sizes

    batch_update_distance_matrix = (
        batch_update_numpy_distance_matrix  # For now we will always use this function
    )

    eps = 0.10  # ToDo Parameterize

    print("***\t***")
    print(f"Starting eps:\t{eps}")

    # Configure logging
    metric = "precomputed"
    clustering_args = dict(eps=eps, min_samples=2, metric=metric, n_jobs=-1)

    batch_time = time.time()

    # report cluster pool metrics
    processed_pool_size = len(label_tracker)
    number_of_singletons = processed_pool_size - cluster_count
    print(f"Number of clusters in pool:\t{cluster_count}")
    print(f"Number of singletons in pool:\t{number_of_singletons}")

    # add this batch to bookkeeping
    processed_pool_sizes.append(processed_pool_size)

    label_tracker.extend(
        [(str(uuid.uuid4()), [doc["id"]]) for i, doc in enumerate(records)]
    )

    is_cluster.extend([False for _ in range(len(records))])

    # Size of existing cluster_pool.
    old_size = len(embeds) if embeds is not None else 0

    # update embedding list
    new_embeds = [doc["concat_embedding"] for doc in records]

    if embeds is not None:
        embeds.extend(new_embeds)
    else:
        embeds = new_embeds

    unique_article_id += len(records)  # increment by number of samples added

    # get distances from new samples to old samples
    # M X [[N], [M]] = M x N+M matrix
    # TODO: This implementation vs. Database
    # TODO: Thresholding to make it more sparse
    add_to_distance_matrix = batch_update_distance_matrix(
        np.ascontiguousarray(new_embeds),
        cluster_pool=np.ascontiguousarray(embeds),
    )

    # Convert (M, N+M) -> (N+M, N+M), make sparse if possible
    if distance_matrix is None:
        distance_matrix = add_to_distance_matrix
    else:
        distance_matrix = get_sparse_distance_matrix(
            add_to_distance_matrix, old_size if old_size > 0 else None
        )

    # Cluster
    clusterer = DBSCAN(**clustering_args).fit(distance_matrix)

    # Update clusters and singletons
    update_time = time.time()
    unique_labels = np.unique(clusterer.labels_)
    to_remove = set()
    updated_clusters = []  # Indicies to update database

    # Cluster formation
    for label in unique_labels:
        if label != -1:
            indices = np.nonzero(clusterer.labels_ == label)[0]

            update_idx = indices[0]

            # * Don't need for DB
            to_remove.update(
                [i for i in indices[1:] if not is_cluster[i]]
            )  # keep track of items to remove from all items

            added_articles = [
                label_tracker[id_idx][1][0]
                for id_idx in indices[1:]
                if not is_cluster[id_idx]
            ]

            updated_clusters.append((label_tracker[update_idx][0], added_articles))

            # extend first instance with all like labels
            label_tracker[update_idx][1].extend(added_articles)

            # rename if not labeled cluster yet
            if is_cluster[update_idx] is False:
                cluster_count += 1

                unique_cluster_id += 1
                is_cluster[update_idx] = True

            # Update embeddings with the mean of all the embeddings in cluster
            embeddings_for_this_cluster_label = [embeds[id_idx] for id_idx in indices]

            centroid = np.mean(embeddings_for_this_cluster_label, axis=0)
            embeds[update_idx] = centroid.tolist()

    print(f"update_time:\t{time.time() - update_time}")

    # delete indices that were merged
    cleanup_time = time.time()
    update_label_time = time.time()

    label_tracker = [
        label_tracker[i] for i in range(len(label_tracker)) if i not in to_remove
    ]

    is_cluster = [is_cluster[i] for i in range(len(is_cluster)) if i not in to_remove]
    print(f"Labeling cleanup\t{time.time() - update_label_time:.2f}")

    embed_cleanup = time.time()
    embeds = [e for i, e in enumerate(embeds) if i not in to_remove]

    print(f"embed cleanup\t{time.time() - embed_cleanup:.2f}")
    print(f"cleanup_time:\t{time.time() - cleanup_time}")

    # Track times
    batch_time = time.time() - batch_time
    batch_times.append(batch_time)
    print(f"Batch time:\t{batch_time}")
    print(f"mean batch time:\t{sum(batch_times)/len(batch_times)}")

    # dont use aggregated variables here, recalculate to double check accuracy
    number_of_clusters = len(np.nonzero(is_cluster)[0])
    number_of_singletons = len(np.nonzero(~np.asarray(is_cluster, dtype=bool))[0])
    print(f"Number of clusters\t{number_of_clusters}")
    print(f"Number of singletons\t{number_of_singletons}")

    number_of_stories_in_saved = sum([len(samples[1]) for samples in label_tracker])
    print(f"total_stories_clustered\t{number_of_stories_in_saved}")

    new_entries_articles = [
        label_tracker[i]
        for i in range(old_size, len(label_tracker))
        if is_cluster[i] is False
    ]

    total_new_articles = sum([len(a[1]) for a in new_entries_articles])
    print("Total New Articles Actual", total_new_articles)
    print("Total New Articles Expected", len(new_entries_articles))
    return new_entries_articles, updated_clusters
