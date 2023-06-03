from src.ReportParser import PerfReportUnparser
from src.common.functions import write_to_file


def write_to_unparser(combined_information, common_fields, args):
    text = PerfReportUnparser(args.field_separator, common_fields)\
        .unparse(combined_information)
    write_to_file("Writing to file", args.output, text)


def write_sorted_list(sorted_list):
    write_to_file("Writing sorted list to file", "sorted", sorted_list)


def write_to_linker_template(template_path, sorted_list, debug):
    lookup_text = "} :text ="
    spaces = 2 * " "

    # get information into correct style
    for index, line in enumerate(sorted_list):
        sorted_list[index] = f"{spaces}*(.text.{line})"

    if debug:
        sorted_list.insert(0, f"{spaces}__hfsort_start = .;")
        sorted_list.append(f"{spaces}__hfsort_end = .;")

    sorted_list.append(f"{spaces}*(.text*)")

    # get template file content
    with open(template_path, "r") as f:
        backup = [line.rstrip('\n') for line in f]

    # insert custom text into content
    for num, text in enumerate(backup):
        if lookup_text in text:
            # split backup at index of lookup_text
            # and insert the sorted_list
            higher_half, lower_half = backup[:num], backup[num:]
            backup = higher_half + sorted_list + lower_half
            break

    write_to_file("Writing information to file", "vmlinux.lds", backup)


def write_linker_script(sorted_list):
    # get sorted_list in correct style
    spaces = 2 * " "
    for index, line in enumerate(sorted_list):
        sorted_list[index] = f"{spaces}*(.text.{line})"

    text_block = """SECTIONS
{{
  .text : {{
{sorted_list}
  }}
  *(.text*)
}}
    """.format(sorted_list="\n".join(sorted_list))

    write_to_file("Writing sorted list to file", "hfsort.ld", text_block)


def write_missing_symbols_list(extension, inputfile, missing_symbols):
    """
    Generate the debug file which shows in a copy of the sorted_list
    the missing symbols. For that prupose append 'missing -- ' to
    the line.
    """

    with open(inputfile, "r") as f:
        backup = [line.rstrip('\n') for line in f]

    for num, line in enumerate(backup):
        if not line:
            continue

        for symbol in missing_symbols:
            if not symbol:
                continue

            if symbol in line:
                backup[num] = f"missing -- {line}"

    write_to_file("Write symbols to file", f"missing-{extension}", backup)
