from collections import namedtuple
from getpass import getpass
from subprocess import run, PIPE


def calculate_size_from_systemmap(parsed_map):
    """
    Find symbol in systemmap and calculate symbol size (in byte) from the next
    symbol in the list.

    Returns
        A dict of the form {symbol_name: symbol_size}
    """

    sysmap_list, total_length = {}, len(parsed_map)

    for index, element in enumerate(parsed_map):
        address, symbol_type, symbol = element.address, element.symbol_type, \
            element.symbol

        if symbol_type not in ["t", "T"]:
            continue

        if index + 1 > total_length:
            print(f"WARNING Symbol size of symbol '{symbol}' will be set to  "
                  f"zero because of missing addresses. Check for problems.")
            sysmap_list[symbol] = 0
            continue

        next_address = parsed_map[index + 1].address
        sysmap_list[symbol] = int(next_address, 16) - int(address, 16)

    return sysmap_list


def get_kallsyms_output():
    """
    Get output from /proc/kallsyms.

    Returns:
        A list containing the lines of the output from /proc/kallsyms.
    """

    process = run('sudo -S cat /proc/kallsyms'.split(),
                  input=getpass("[sudo] Password: "),
                  stdout=PIPE,
                  stderr=PIPE,
                  universal_newlines=True,
                  encoding="ascii"
                  )

    # split the output string at the newline character and
    # make a generator out of it
    return process.stdout.split('\n')


def parse_size_map(line):
    """
    Parse the information created from *nm -S vmlinux*.

    Returns
        If the line has the wanted values it returns the values, if not None.
    """

    split_line = line.split()

    if len(split_line) == 4:
        # row has values address, size, symbol_type, symbol
        _, size, symbol_type, symbol = split_line
        return size, symbol_type, symbol

    return None


def parse_default_systemmap(line):
    """
    Parse information created /proc/kallsyms or written in System.map.

    Returns
        If the line has the wanted values it returns the values, if not None.
    """

    split_line = line.split()
    length = len(split_line)

    if length == 3:
        # row has values address, symbol_type, symbol
        address, symbol_type, symbol = split_line
    elif length == 4:
        # row has values address, symbol_type, symbol, module_name
        address, symbol_type, symbol, _ = split_line
    else:
        print(f"ERROR Not recognized format of line '{line}'")
        return None

    return address, symbol_type, symbol


def parse_systemmap(generator, symbols_only=False, size_map=False, nm_s=False):
    """
    Parses the information from multiple systemmap types (System.map,
    /proc/kallsyms and *nm -S vmlinux*). If no additional flags are specified
    the function returns a list of namedtuple with values (address,
    symbol_type, symbol).

    Args and Returns:
        generator: Generator of the systemmap.
        symbols_only: Returns a sorted list of only symbol names. Can only
        be used by the types System.map and /proc/kallsyms.
        size_map: Returns a dict in the form {symbol_name: symbol_size}. Only to
        be used with the types System.map and /proc/kallsyms.
        nm_s: Returns a dict in the form {symbol_name: symbol_size}. Only to
        be used with the type *nm -S vmlinux*.

    """

    if not generator:
        return None

    sysmap_list = {} if nm_s else []
    element = namedtuple("sysmap", ["address", "symbol_type", "symbol"])

    for line in generator:
        if not line:
            continue

        information = parse_size_map(line) if nm_s else \
            parse_default_systemmap(line)

        if information is None:
            continue

        size, symbol_type, symbol = information
        if nm_s:
            if symbol_type not in ["t", "T"]:
                continue

            sysmap_list[symbol] = int(size, 16)
            continue

        # else parse the default file
        address = size
        sysmap_list.append(element(address, symbol_type, symbol))

    if nm_s:
        return sysmap_list

    # sort systemmap after addresses because of possible swapped entries
    sysmap_list = sorted(sysmap_list, key=lambda x: x.address)

    if symbols_only:
        # if only symbols are wanted clean up the sysmap_list
        return [item
                for item in sysmap_list
                if item.symbol_type in ["t", "T"]]

    return calculate_size_from_systemmap(
        sysmap_list) if size_map else sysmap_list


if __name__ == "__main__":
    """
    For debugging purposes get the first argument from the command line and try
    to parse it.
    """
    from argparse import ArgumentParser
    from common.functions import create_input_file_generator

    parser = ArgumentParser()
    parser.add_argument('-k', '--kallsyms',
                        action="store_true",
                        default=False)

    parser.add_argument('-S', '--sizefile',
                        dest='sizefile',
                        default=None,
                        type=str)

    parser.add_argument('-I', '--system-map',
                        dest='systemmap',
                        default=None,
                        type=str)

    args = parser.parse_args()

    if args.systemmap:
        file = create_input_file_generator(args.systemmap)
        parsed_list = parse_systemmap(file)

    if args.sizefile:
        file = create_input_file_generator(args.sizefile)
        parsed_list = parse_systemmap(file, nm_s=True)

    if args.kallsyms:
        file = get_kallsyms_output()
        parsed_list = parse_systemmap(file)
