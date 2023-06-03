from os import R_OK, access

from pathlib import Path
from re import compile


def create_input_file_generator(file_path):
    """
    Create a generator from the provided file.

    Args:
        file_path: The path to the input file.

    Returns:
        str: Each line of the file, stripped of leading and trailing whitespace.
    """

    if not file_path:
        exit("No file provided.")

    error, file = try_to_open_file(file_path)

    if error:
        exit(f"Could not open file {file}")

    with open(file, 'r') as file:
        for line in file:
            # strip right and left whitespace from line
            yield line.strip()


def try_to_open_file(filepath):
    """
    Try to open the file.

    Args:
        filepath (str): The path to the file.

    Returns:
        Tuple: A tuple containing two values.
            The first value indicates whether the file access was
            unsuccessful (True) or successful (False).
            The second value is either None (if no file path is provided)
            or the resolved Path object.
    """

    if not filepath:
        return False, None

    path = Path(filepath).resolve()
    return not access(path, R_OK), path


def write_to_file(message, filename, text):
    """
    Writes the specified text to the specified file.

    Args:
        message: Message to be written.
        filename: Name of the file to write.
        text: Text content to be written. If a list is provided, it will be
        joined into a string with newlines.

    """
    if type(text) == list:
        text = "\n".join(text)

    print(f"{message} '{filename}'")

    with open(filename, 'w') as f:
        f.write(text)


def exit_handler(_, __):
    exit()


pattern = compile(r'^0x[0-9a-fA-F]+$')  # regex for hex values
def is_hex(string):
    """
    Check if a string represents a hex value in the form of e.g., 0xffAabb99.
    The pattern to check against is defined in the variable pattern.

    Args:
        string: The string to check.

    Returns:
        bool: True if the string represents a hex value, False otherwise.

    """
    return bool(pattern.match(string))


def find_common_items_in_list(list_of_lists):
    """Find common items in given list of lists."""
    return list(set.intersection(*map(set, list_of_lists)))
