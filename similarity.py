#!/usr/bin/env python
import logging
import signal

from argparse import ArgumentParser

from src.FileWriter import write_missing_symbols_list
from src.common.functions import exit_handler, create_input_file_generator
from src.SystemmapParser import get_kallsyms_output, parse_systemmap


def parse_to_information(file, file_type):
    """
    Parse the file to a generator depending on its type. After that parse the
    generator to usable information.

    Returns:
        Returns a sorted list (sorted after the addresses of the symbols) of
        all the symbol names.
    """

    if not file or not file_type:
        exit(f"No object '{file}' of type '{file_type}' provided.")

    generator = None

    if file_type in ["file", "sorted-list"]:
        # if object is a type of file create a file_generator
        print(f"Parse file '{file}'...")
        generator = create_input_file_generator(file)

        if file_type == "sorted-list":
            # remove any debugging symbols from the sorted_list
            return [line.lstrip("#").lstrip("+").strip()
                    for line in list(generator)
                    if line]

    if file_type == "kallsyms":
        # Because the output is from /proc/kallsysms, no files need to be
        # opened and therefore no generators need to be created.
        print("Get and parse /proc/kallsyms...")
        generator = file

    return parse_systemmap(generator, symbols_only=True)


def check_missing_symbols(sorted_list, sysmap):
    """
    Try to find the symbols defined in sorted_list. Depending on if it is found
    in the systemmap sort it into one of the bins.
    """

    same_symbols, missing_symbols = [], []
    sysmap_symbol_list = [element.symbol for element in sysmap]

    for symbol in sorted_list:
        if not symbol:
            continue

        if symbol in sysmap_symbol_list:
            same_symbols.append(symbol)
        else:
            missing_symbols.append(symbol)

    return same_symbols, missing_symbols


def find_borders(args, sysmap):
    """
    Finds the starting and ending indices of a contiguous region of symbols in
    the sysmap based on the addresses of the first and last items in the
    sorted list.

    Args:
        args: Object containing the arguments.
        sysmap: A list containing systemmap information.

    Returns:
        A tuple containing the start and end indices of the contiguous region.
    """

    start_index = [index
                   for index, element in enumerate(sysmap)
                   if element.symbol == args.startsymbol]

    if not start_index:
        print(f"ERROR Start symbol '{args.startsymbol}' not found.")
        return None, None

    end_symbol = args.endsymbol
    end_index = [index
                 for index, element in enumerate(sysmap)
                 if element.symbol == end_symbol]

    if not end_index:
        print(f"ERROR End symbol '{end_symbol}' not found.")
        return None, None

    return start_index[0], end_index[0]


def check_out_of_order_symbols(args, sorted_list, sysmap):
    """
    Checks for symbols that are out of order within the contiguous region
    defined by the start and end indices.

    Args:
        args: Object containing the arguments.
        sorted_list: The list of sorted symbols.
        sysmap: A list containing systemmap information.

    Returns:
        A tuple containing two lists. A list of found_symbols which there found
        in the contiguous region and a list missing_symbols of not found
        symbols in the contiguous region.
    """

    found_symbols, missing_symbols = [], []
    start_index, end_index = find_borders(args, sysmap)

    if start_index is None or end_index is None:
        return None, None

    for symbol in sorted_list:
        found = False
        for element in sysmap[start_index:end_index]:
            if symbol == element.symbol:
                found_symbols.append(symbol)
                found = True
                break

        if not found:
            missing_symbols.append(symbol)

    return found_symbols, missing_symbols


def find_similarity(args, sorted_list, sysmap):
    same_symbols, missing_symbols = check_missing_symbols(sorted_list, sysmap)

    print(
        f"Similarity: {(len(same_symbols) / len(sorted_list)) * 100:.2f}%\n"
        f"{len(missing_symbols)} missing symbols from a total "
        f"of {len(sorted_list)} symbols."
    )

    if args.loglevel == logging.DEBUG:
        write_missing_symbols_list("similarity", args.inputfile,
                                   missing_symbols)

    return missing_symbols


def find_out_of_order(args, sorted_list, sysmap):
    found_symbols, missing_symbols = \
        check_out_of_order_symbols(args, sorted_list, sysmap)

    if found_symbols is None or missing_symbols is None:
        print("Out-of-order test cant be executed because of missing debug "
              "symbol in the systemmap.")
        return None

    print(
        f"Out-of-order symbols:"
        f" {(len(found_symbols) / len(sorted_list)) * 100:.2f}%\n"
        f"{len(missing_symbols)} symbols which are not in order from a total "
        f"of {len(sorted_list)} symbols."
    )

    if args.loglevel == logging.DEBUG:
        write_missing_symbols_list("out-of-order", args.inputfile,
                                   missing_symbols)

    return missing_symbols


def calculate_final_ranking(sorted_list, missing):
    """
    Calculates the final ranking by removing the symbols from the sorted list
    that could not be found in the systemmap.

    sorted_list: A list of symbols sorted in a specific order.
    missing_ooo: A list of symbols missing in the contiguous region.
    missing_similarity: A list of symbols missing in the systemmap but
    are defined in the sorted list.
    """

    # find difference of two lists
    missing_ooo, missing_similarity = missing
    missing_list = list(set(missing_ooo) - set(missing_similarity))

    len_sorted, len_missing = len(sorted_list), len(missing_list)
    print(
        f"\nFinal ranking: {(1 - (len_missing / len_sorted)) * 100:.2f}%\n"
        f"{len_missing} missing symbols from the continuous region from a "
        f"total of {len_sorted} symbols."
    )


def start(args):
    input_data = parse_to_information(args.inputfile, "sorted-list")

    if args.kallsyms:
        output_data = parse_to_information(get_kallsyms_output(), "kallsyms")
    else:
        output_data = parse_to_information(args.systemmap, "file")

    print("\nCalculate similarity...")
    missing_similarity = find_similarity(args, input_data, output_data)
    print("\nFind symbols which are not in order...")
    missing_ooo = find_out_of_order(args, input_data, output_data)

    if missing_ooo is None or missing_similarity is None:
        print("Final ranking test cant be executed because of missing "
              "information.")
        return None

    calculate_final_ranking(input_data, (missing_ooo, missing_similarity))


def main():
    signal.signal(signal.SIGINT, exit_handler)

    parser = ArgumentParser(
        description="Check a generated *sorted* file against a e.g. "
                    "System.map file to verify if symbols are missing or in "
                    "the correct order after compilation")

    parser.add_argument('-i', '--sorted-file',
                        help="Specify the original sorted layout file as a "
                             "reference.",
                        dest="inputfile",
                        required=True,
                        type=str)

    parser.add_argument('-I', '--system-map',
                        help="Specify a System.map file with the real "
                             "layout to check against.",
                        dest="systemmap",
                        type=str)

    parser.add_argument('-k', '--kallsyms',
                        help="Use the output from /proc/kallsyms to check "
                             "against the real layout of the running kernel.",
                        action="store_true",
                        default=False)

    optional = parser.add_argument_group("Optional")
    optional.add_argument('-S', '--start-symbol',
                          help="Define the symbol in the symbol file that marks "
                               "the beginning of the custom layout in the "
                               ".text section. Default: __hfsort_start",
                          dest="startsymbol",
                          default="__hfsort_start",
                          type=str)

    optional.add_argument('-e', '--end-symbol',
                          help="Define the end symbol in the symbol file that "
                               "marks the end of the custom layout in the "
                               ".text section.  Default: __hfsort_end",
                          dest="endsymbol",
                          default="__hfsort_end",
                          type=str)

    optional.add_argument('-d', '--debug',
                          help="Generate debugging statements. Additionally, "
                               "files are generated that show detailed "
                               "information based on the tested property.",
                          action="store_const",
                          dest="loglevel",
                          const=logging.DEBUG)

    args = parser.parse_args()

    if not args.systemmap and args.kallsyms is False:
        exit("One of the two flags --system-map or --kallsyms needs "
             "to be provided.")

    start(args)


if __name__ == "__main__":
    main()
