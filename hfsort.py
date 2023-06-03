#!/usr/bin/env python
import signal
import logging
from sys import exit

from argparse import ArgumentParser
from src.common.classes import Node, Predecessor
from src.common.functions import create_input_file_generator, exit_handler, \
    is_hex
from src.ReportParser import PerfReportParser
from src.C3Algorithm import HFSorter
from src.FileWriter import write_sorted_list, write_to_linker_template, \
    write_linker_script
from src.SystemmapParser import get_kallsyms_output, parse_systemmap


def get_size_list(args):
    """
    Depending on the set flag get all symbols with their symbol size.

    Returns:
        If a flag is set and the parsing proceeded smoothly return a dict of
        form {symbol_name: symbol_size}, else None.
    """

    symbol_size_list = None

    if args.kallsyms:
        print("Get and parse /proc/kallsyms...")
        symbol_size_list = parse_systemmap(get_kallsyms_output(), size_map=True)

        if not symbol_size_list:
            exit("ERROR No valid output from /proc/kallsyms. "
                 "Check for problems.")

    if args.sizefile:
        print(f"Parse sizefile '{args.sizefile}'...")
        file = create_input_file_generator(args.sizefile)
        symbol_size_list = parse_systemmap(file, nm_s=True)

    return symbol_size_list


def get_symbol_size(element, symbol_size_list, ta_sy, debug):
    """
    Get the symbol size of the symbol name. Symbol size can be provided via the
    element itself or via a sizefile.

    Returns
        If a symbol size got successfully found the return has an int of value
        symbol size, else None.
    """
    not_found_size_symbol, debug = debug

    if not symbol_size_list:
        # element got itself a symbol_size
        return int(element.get("symbol_size")), not_found_size_symbol

    symbol_size = symbol_size_list.get(ta_sy)
    if symbol_size is None:
        if debug:
            not_found_size_symbol += 1
            print(f"DEBUG Symbol size of '{ta_sy}' not found in the "
                  f"size list. Trying to get the information from the element "
                  f"itself."
                  )

        # if symbol name is not provided in the sizefile try if element itself
        # has size information
        symbol_size = element.get("symbol_size")
        if symbol_size is None:
            if debug:
                print(f"DEBUG Symbol size of '{ta_sy}' could not be "
                      f"determined.")

            # if it has not dismiss the try
            return None, None

    return int(symbol_size), not_found_size_symbol


def parse_and_combine_information_from_multiple_files(args, report_list):
    """
    Combine the report information from the report list into usable information
    for the C3 heuristic.

    It checks for an interesting section in the report and analyses the
    target symbols aka nodes. For each unique node, related data in the
    report is collected like predecessor, symbol_size, global samples, etc.
    This information is used to build up an internal representation of the
    directed weighted call graph from the report.

    Args:
        args: Class of set arguments.
        report_list: List of parsed report file.
        debug: Set (or not set) debug flag.

    Returns:
        A list of nodes containing the collected information.

    """

    if not report_list.sections:
        exit("ERROR: No section available.")

    # find interesting section
    section = None
    for section in report_list.sections:
        if "cycles" or "instructions" in section.header.get("event_name"):
            # find the first interesting section and use it
            break
    if not section:
        exit("ERROR: No suitable section found")

    debug = args.loglevel == logging.DEBUG

    node_list, examined_nodes = [], []
    total_samples = int(section.header.get("total_samples"))
    symbol_size_list = get_size_list(args)

    # debugging statistics
    not_found_size_symbols, correct_symbols, hex_symbols = 0, 0, 0

    for element in section.values:
        ta_sy = element.get("target_symbol")

        # Skip target symbols that have already been examined
        if ta_sy in examined_nodes:
            continue

        # Check if target symbol is a hex value or if function size is defective
        # We only want valid symbol names, so if it is corrupted data, skip it
        if is_hex(ta_sy):
            examined_nodes.append(ta_sy)
            hex_symbols += 1
            continue

        correct_symbols += 1

        symbol_size, not_found_size_symbols = \
            get_symbol_size(element, symbol_size_list, ta_sy,
                            (not_found_size_symbols, debug))

        if symbol_size in [0, "unknown", None]:
            if debug:
                not_found_size_symbols += 1
                print(f"DEBUG Symbol size of '{ta_sy}' not found in the"
                      f"size list.")

            examined_nodes.append(ta_sy)
            continue

        node = \
            create_new_node(section.values, symbol_size, ta_sy, total_samples)
        node_list.append(node)

        # save target_symbol because it is fully examined
        examined_nodes.append(ta_sy)

    if args.loglevel in [logging.INFO, logging.DEBUG]:
        print(f"INFO Total amount of hex lines: {hex_symbols}\n"
              f"INFO Total number of target symbols with missing sizes in "
              f"the sizefile: "
              f"{not_found_size_symbols}\n"
              f"INFO Total number of valid lines before getting the size: "
              f"{correct_symbols}\n"
              f"INFO Percentage of target symbols with missing sizes to "
              f"valid lines: "
              f"{(not_found_size_symbols / correct_symbols) * 100:.2f}%")

    return node_list


def create_new_node(values, symbol_size, ta_sy, total_samples):
    """
    Create a new node. Collect all the information for this node from the call
    graph.
    """

    node = Node(function_name=ta_sy, size=symbol_size)

    for el in values:
        if el.get("target_symbol") == ta_sy:
            # found entry where ta_sy is the target_symbol of the element
            node.add_samples(el.get("samples"), total_samples)

            if el.get("source_symbol") != ta_sy:
                # If the source_symbol is different from the target_symbol,
                # add it as a predecessor
                node.add_predecessor(Predecessor(el, total_samples))
    return node


def start(args):
    print("Parse report...")

    report = create_input_file_generator(args.report)
    parsed_file = PerfReportParser(args.field_separator).parse(report)

    print("Create nodes...")
    parsed_info = \
        parse_and_combine_information_from_multiple_files(args, parsed_file)

    sorter = HFSorter(args, parsed_info)
    print("Sorting...")
    sorted_list = sorter.sort()

    write_sorted_list(sorted_list)

    debug = args.loglevel == logging.DEBUG

    if debug:
        # remove debugging characters
        sorted_list = [line.lstrip("#").lstrip("+").strip()
                       for line in sorted_list]

    if args.linker_script:
        write_linker_script(sorted_list.copy())

    if args.template:
        write_to_linker_template(args.template, sorted_list.copy(), debug)


def main():
    signal.signal(signal.SIGINT, exit_handler)

    parser = ArgumentParser(
        description='Heuristic Sort - Sorts a single report file into a sorted '
                    'list using the C3 heuristic. Outputs the sorted list to '
                    'the "sorted" file.'
    )

    parser.add_argument('-r', '--report',
                        help="Specify the report file containing observed "
                             "samples for each caller-callee call. The fields "
                             "samples, source_symbol and target_symbol are "
                             "required.",
                        required=True,
                        type=str)

    parser.add_argument('-l', '--linker-script',
                        help="Output the sorted list in a simple linker script "
                             "format. Inserts the symbols in the "
                             "form *(.text.symbol).",
                        action="store_true",
                        default=False)

    parser.add_argument('-t', '--template',
                        help="Integrate the sorted list into a template "
                             "vmlinux.lds file. Inserts the symbols in the "
                             "form *(.text.symbol) at the end of the "
                             ".text section ending in *(.text*). If debug "
                             "is enabled include the symbols "
                             '__hfsort_start and __hfsort_end for use '
                             'in similarity.py.',
                        default=None,
                        type=str)

    fine_tuning = parser.add_argument_group("Fine-Tuning")
    fine_tuning.add_argument('-f', '--field-separator',
                             help="Specify the field seperator which was used "
                                  "in the report file. "
                                  "Default: $",
                             default='$',
                             dest='field_separator',
                             type=str)

    fine_tuning.add_argument('-p', '--min-probability',
                             help="Set the minimum probability for an arc to "
                                  "be considered relevant. The weight of an "
                                  "arc is calculated by dividing its own "
                                  "number of samples by the total number of "
                                  "samples. "
                                  "Default: 0.1",
                             default=None,
                             dest='k_min_prob',
                             type=float)


    fine_tuning.add_argument('-P', '--page-size',
                             help="Set the page size according to which the "
                                  "C3 heuristic sets the maximum "
                                  "cluster size. "
                                  "Default: 4096 [byte]",
                             default=4096,
                             dest='pagesize',
                             type=int)

    optional = parser.add_argument_group("Optional")
    optional.add_argument('-k', '--kallsyms',
                          help="Use the output from /proc/kallsyms to "
                               "calculate the symbol sizes from. However, it "
                               "provides only an upper bound for the symbol "
                               "size, i.e. it is not bit precise.",
                          action="store_true",
                          default=False)

    optional.add_argument('-S', '--sizefile',
                          help="Specify a generated symbol size file that "
                               "represents precise symbol sizes of all symbols "
                               "in the kernel. The file can be created using "
                               "the command 'nm -S vmlinux > sizefile'.",
                          dest='sizefile',
                          default=None,
                          type=str)

    optional.add_argument('-v', '--verbose',
                          help="Enable verbose statements.",
                          action="store_const",
                          dest="loglevel",
                          const=logging.INFO)

    optional.add_argument('-d', '--debug',
                          help="Enable debugging statements and debugging "
                               "information in files.",
                          action="store_const",
                          dest="loglevel",
                          const=logging.DEBUG)

    args = parser.parse_args()

    if args.kallsyms and args.sizefile:
        exit("--sizefile and --kallsyms can't be used together. "
             "Only one option can be used to enhance the information.")

    start(args)


if __name__ == "__main__":
    main()
