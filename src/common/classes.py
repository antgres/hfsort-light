from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Iterable


@dataclass
class Node:
    """
        Represents a node in the graph from the perspective of the callee.

        Args:
            function_name: The name of the callee function.
            size: The size of the calle function in bytes.
            global_samples: The sum of total samples which are connected to
            the node, i.e. in how many samples was this node called.
            Defaults to 0.
            normalized_weight: The weight of the node in the global context.
            Defaults to 0.
            predecessor: List of predecessor nodes which call this node.
            Defaults to an empty list.

        Methods:
            add_samples:
                Adds the samples of the node and updates the normalized weight.
            add_predecessor:
                Adds a predecessor node to the current node.
            get_biggest_predecessor():
                Returns the predecessor node with the highest number of
                samples to the target.
        """

    function_name: str
    size: int  # bytes
    # samples of the node in a global context, i.e. the sum of all
    # predecessor samples to the node and from the node to the node itself
    global_samples: int = 0
    global_weight: int = 0
    predecessors: list = field(default_factory=list)

    def __eq__(self, other):
        return self.function_name == other.function_name

    def add_samples(self, samples, total_samples):
        self.global_samples += samples
        self.global_weight = round(self.global_samples / total_samples, 4)

    def add_predecessor(self, predecessor: 'Predecessor'):
        self.predecessors.append(predecessor)

    def get_biggest_predecessor(self):
        if not self.predecessors:
            # no predecessors defined
            return None

        return max(self.predecessors, key=lambda x: x.samples_to_target)


@dataclass
class Predecessor:
    """
    Represents a predecessor (caller) function.

    Attributes:
        function_name: The name of the predecessor function.
        samples_to_target: The number of samples from the predecessor function
        to the target function (node).
        weight_to_target: The weight of the predecessor function as a
        percentage of total samples.

    """

    function_name: str
    samples_to_target: int
    weight_to_target: float  # in percentage

    def __init__(self, key_dict, total_samples):
        element = SimpleNamespace(**key_dict)
        self.function_name = element.source_symbol
        self.samples_to_target = element.samples
        # calculate weight in percentage
        self.weight_to_target = (element.samples / total_samples) * 100


@dataclass
class Section:
    """
    Represents a section in the parsed report file.

    Attributes:
        header: Header information per section.
        fields: A list of field names in the section.
        values: An iterable of dictionaries representing the values in the
        section.
    """

    header: dict = field(default_factory=dict)
    fields: list = field(default_factory=list)
    values: Iterable[dict] = field(default_factory=list)


@dataclass
class Metadata:
    """
    Represents the metadata of the parsed report file.

    Attributes:
        header_information: A list of strings containing the header information
        (additional information) from the report file.
        sections: An iterable of Section instances representing the sections
        in the report.
    """
    header_information: list = field(default_factory=list)
    sections: Iterable[Section] = field(default_factory=list)
