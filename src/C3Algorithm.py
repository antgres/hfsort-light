import logging
from sys import exit
from src.common.classes import Node


class Cluster:
    """
    Cluster definition for the C3 heuristic.

    Attributes:
        PAGE_SIZE: Page size in bytes. Defaults to 4KiB.
        K_CALLER_DEGRADE_FACTOR: Factor determining how much a caller cluster
        is willing to degrade its own density to include another cluster.
        density: Density of the cluster.
        total_time: Total time spent executing functions in the cluster. Assumed
        it is equivalent to the total sum of samples.
        total_size: Total size in bytes of the cluster.
        nodes: List of nodes in the cluster.

    Methods:
        check_cluster_merge(other_cluster):
            Check if the cluster can be merged with another cluster. If it
            possible return True, else False

    """

    # The density of the cluster is defined as
    # Total_amount_spent_executing_functions(Cluster) divided
    # by Total_size_in_bytes(Cluster)
    density = 0

    total_time = 0
    total_size = 0

    def __init__(self, node: Node, pagesize):
        self.page_size = pagesize # default: 4KiB

        # Factor to determine by how much a caller cluster is willing to degrade
         # its density by merging a callee.
        self.k_caller_degrade_factor = 8

        self.nodes = [node]
        self._update_density()

    def check_cluster_merge(self, other_cluster: 'Cluster'):
        # if the sum is bigger than MERGING_THRESHOLD prohibit the merge
        if self.total_size + other_cluster.total_size > self.page_size:
            return True

        # check if the merge results in a better density
        new_density = (self.total_time + other_cluster.total_time) / \
                      (self.total_size + other_cluster.total_size)

        if self.density > new_density *  self.k_caller_degrade_factor:
            # if merge results in a poorer density even with degrade factor
            # stop the merge
            return True

        self.nodes += other_cluster.nodes
        self._update_density()

        return False

    def _update_size(self):
        """Calculate the total size of all callees in bytes."""
        self.total_size = sum(node.size for node in self.nodes)

    def _update_time(self):
        # it is assumed that the total time of a function is equal to the sum
        # of its combined incoming arcs
        self.total_time = sum(node.global_samples for node in self.nodes)

    def _update_density(self):
        self._update_time()
        self._update_size()
        self.density = round(self.total_time / self.total_size, 4)


class HFSorter:
    """
    Sort the parsed data with the C3 heuristic.

    The heuristic can be found in
    https://github.com/facebook/hhvm/blob/master/hphp/util/hfsort.cpp

    Attributes:
        K_MIN_ARC_PROBABILITY: The minimum approximate probability (weight) of
        a callee for being considered for merging with the caller's cluster.
        node_list: List of nodes, which are sorted in weight order.
        cluster_list: List of clusters.
        debug: Flag indicating whether debug information is enabled.
        linker: Flag indicating whether a linker script is wanted as output. If
        it is wanted do not print debug information.

    """

    # The minimum approximate probability (weight) of a callee for being
    # considered for merging with the caller's cluster.
    K_MIN_ARC_PROBABILITY: float = 0.1

    def __init__(self, args, node_list):
        self.node_list = sorted(node_list, key=lambda x: x.global_samples,
                                reverse=True)
        self.cluster_list = [Cluster(node, args.pagesize) for node in node_list]

        if args.k_min_prob is not None:
             self.k_caller_degrade_factor = args.k_min_prob

        self.loglevel = args.loglevel

    def _merge_clusters(self, source_index, target_index):
        """Try to merge the clusters."""

        source_cluster = self.cluster_list[source_index]
        target_cluster = self.cluster_list[target_index]

        rejected = source_cluster.check_cluster_merge(target_cluster)
        if rejected:
            # merge is not good so do not merge
            return

        # update source_cluster in cluster_list
        self.cluster_list[source_index] = source_cluster
        # remove target_cluster from list
        # delete target_cluster after update because of changing
        # length of cluster_list after removal
        del self.cluster_list[target_index]

    def _get_most_likely_predecessor(self, target_node):
        """
        Get the predecessor (caller) with the biggest samples (weight)
        for the given node.
        """

        predecessor = target_node.get_biggest_predecessor()
        if not predecessor:
            # no predecessors found so return
            return None

        # check if the given weight is meaningful to consider
        # for a merge
        if predecessor.weight_to_target < self.K_MIN_ARC_PROBABILITY:
            return None

        # look for the node with the same function_name else return None
        return next((node for node in self.node_list
                     if node.function_name == predecessor.function_name),
                    None)

    def _find_cluster(self, node):
        """Find the cluster in which the searched for node is included."""
        for index, cluster in enumerate(self.cluster_list):
            for cluster_node in cluster.nodes:
                if cluster_node == node:
                    return index
        # Because every node is by definition in a cluster stop the sorting
        # if this is not the case
        exit(f"ERROR Cluster index for node {node.function_name} "
             f"could not be found")

    def _sort_functions_in_clusters(self):
        """
        Sort clusters by density and write functions according to the density
        order into a list. Depending on the set flags append debug characters
        to the symbol.
        """
        sorted_function_names = []
        debug = self.loglevel == logging.DEBUG

        # append debug characters if debug flag is set
        symbols = ["+", "#"] if debug else [None, None]

        for index, cluster in enumerate(sorted(self.cluster_list,
                                               key=lambda x: x.density,
                                               reverse=True)):
            symbol = symbols[index % 2]  # change symbol if in next cluster
            for node in cluster.nodes:
                text = f"{symbol}  {node.function_name}" if debug \
                    else node.function_name
                sorted_function_names.append(text)

        return sorted_function_names

    def sort(self):
        # Sort incoming report data with call-chain clustering heuristic
        # defined in the paper "Optimizing function placement for
        # large-scale data-center applications"
        # Source: https://dl.acm.org/doi/abs/10.5555/3049832.3049858
        #
        # The original source code can be found at
        # https://github.com/facebook/hhvm/blob/master/hphp/util/hfsort.cpp
        #
        # Steps
        # 0. Put every function in its own cluster
        # 1. Process each function/node in decreasing order of
        #    profile weight/samples
        # 2. Append its most likely predecessor (caller) cluster to its
        #    own cluster
        # 3. Don't merge two clusters if either of them
        #    is larger than MERGING_THRESHOLD (page size)
        # 4. Sort all clusters into decreasing order with no gaps inbetween
        #    according to their density metric
        #    Density(Cluster) = Total_amount_spent_executing_functions(Cluster)/
        #                       Total_size_in_bytes(Cluster)
        #

        index = 0

        for node in sorted(self.node_list,
                           key=lambda x: x.global_samples,
                           reverse=True):

            predecessor_node = self._get_most_likely_predecessor(node)

            if not predecessor_node:
                # no predecessor_node found so continue
                index += 1
                continue

            # find source and target cluster
            source_cluster_index = self._find_cluster(node)
            target_cluster_index = self._find_cluster(predecessor_node)

            if source_cluster_index == target_cluster_index:
                # already in the same cluster
                continue

            self._merge_clusters(source_cluster_index, target_cluster_index)

        if self.loglevel in [logging.INFO, logging.DEBUG]:
            print(f"INFO K_MIN_ARC_PROBABILITY: {self.K_MIN_ARC_PROBABILITY}\n"
                  f"INFO Number of nodes: {len(self.node_list)}\n"
                  f"INFO Number of nodes without most likely "
                  f"predecessor: {index}\n"
                  f"INFO Percentage to total number of "
                  f"nodes: {round((index / len(self.node_list)), 2) * 100}%")

        return self._sort_functions_in_clusters()
