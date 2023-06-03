#!/usr/bin/env python
import signal
import logging

from os import getcwd
from pathlib import Path
from argparse import ArgumentParser

from src.FileWriter import write_to_unparser
from src.ReportParser import PerfReportParser
from src.common.classes import Metadata, Section
from src.common.functions import create_input_file_generator, exit_handler, \
    find_common_items_in_list


def read_all_the_reports(reports, field_separator, debug):
    """Parse all the report files given."""

    parser = PerfReportParser(field_separator)
    parsed_list = []

    for file_path in [Path(report).resolve() for report in reports]:
        file = file_path if debug else Path(file_path).relative_to(getcwd())

        if debug:
            print(f"Parse file {file}...")

        raw_data = create_input_file_generator(file)
        parsed_file = parser.parse(raw_data)
        parsed_list.append(parsed_file)

        parser.clean_parser()

    return parsed_list


def combine_headers(event_name, header_list):
    """
    Combine the information from multiple sections with the same
    event_name.
    """

    new_header = {"event_name": event_name}

    # combine lost samples
    lost_samples = [int(item.get("lost")) for item in header_list]
    new_header["lost"] = sum(lost_samples)

    # combine total samples
    total_samples = [int(item.get("total_samples")) for item in header_list]
    new_header["total_samples"] = sum(total_samples)

    return new_header


def combine_values(event_name, common_fields, values_list, debug):
    """Combine all the sections with the same event_name."""

    hashed_values_list = \
        transform_into_custom_format(common_fields, values_list)
    combined_list = {}

    for index, values in enumerate(hashed_values_list):
        if index == 0:
            # if first list just copy it
            combined_list = values
            continue

        if debug: print(f"Start merging {event_name}...")

        for new_key, new_value in values.items():
            if combined_list.get(new_key):
                add_up_samples(combined_list, new_key, new_value)

            combined_list[new_key] = new_value

    # re-transform back into the usable format from before
    return [values for _, values in combined_list.items()]


def add_up_samples(combined_list, new_key, new_value):
    """Add the sample value from the new dict to the old dict. """

    old_sample = int(combined_list.get(new_key).get("samples"))
    new_sample = int(new_value.get("samples"))

    combined_list.get(new_key)["samples"] = old_sample + new_sample


def filter_for_common(common_fields, item):
    """
    Create a new dict with only the specified common_fields from the item
    dict, i.e. remove the unwanted keys and with it the values.
    """
    return {key: item[key] for key in common_fields}


def transform_into_custom_format(common_fields, values_list):
    """
    Instead of looping over every item in every report to look for a specific
    source symbol and target symbol combination why not just create a custom
    dict of the given items in the form
        key = item['source_symbol'] + item['target_symbol']
        value = item
    """

    new_values_list = []
    for value_list in values_list:
        new_value = {}
        for item in value_list:
            new_key = f"{item.get('source_symbol')}" \
                      f"{item.get('target_symbol')}"
            new_value[new_key] = filter_for_common(common_fields, item)

        new_values_list.append(new_value)
    return new_values_list


def join_sections(reports, common_information, debug):
    """Combine all the sections into a single report."""

    filtered_sections = filter_sections(reports, common_information)
    metadata = Metadata()

    for section_name, sections in filtered_sections.items():
        new_section = Section(
            fields=common_information.get(section_name),
            header=combine_headers(
                section_name,
                [section.header for section in sections]
            ),
            values=combine_values(
                section_name,
                common_information.get(section_name),
                [section.values for section in sections],
                debug
            )
        )

        metadata.sections.append(new_section)

    return metadata


def filter_sections(reports, common_fields):
    """
    Get the sections that are interesting. The interesting sections are
    described in common_fields.
    """

    new_section = {}

    for report in reports:
        for section in report.sections:
            section_name = section.header.get("event_name")

            if section_name not in common_fields.keys():
                continue

            new_section = \
                append_item_to_dict(new_section, section_name, section)

    return new_section


def append_item_to_dict(to_modify_dict, key, value):
    """
    This function appends a new value to a value of type list under a given key
    depending if it is a new key in the dict or if the key is already defined.

    Args:
        to_modify_dict: The dictionary to be modified by appending the value.
        key: The key under which the value should be appended.
        value: The value to be appended to the dictionary.
    """

    if key not in to_modify_dict:
        to_modify_dict[key] = [value]
    else:
        to_modify_dict[key].append(value)
    return to_modify_dict


def check_for_common_fields(reports):
    """
    Create a dict that stores all the common fields which there found for
    every a section_name in every report.
    """

    all_fields = filter_common_fields(reports)

    return {
        key: find_common_items_in_list(fields)
        for key, fields in all_fields.items()
    }


def filter_common_fields(reports):
    """
    Filter out not needed events or fields like dummy or overhead. Save the
    event_name and the common_fields into a dict.
    """

    new_dict = {}

    for report in reports:
        for section in report.sections:
            section_name = section.header.get("event_name")

            if "dummy" in section_name:
                # dummy event has no important information so ignore it
                continue

            fields = section.fields
            # remove overhead field because not interesting
            fields.remove("overhead")

            new_dict = \
                append_item_to_dict(new_dict, section_name, fields)

    return new_dict


def analyse_reports(reports, debug):
    """
    Analyzes a list of reports and identifies common events and fields.
    """

    common_information = check_for_common_fields(reports)

    if debug:
        print("Common events with corresponding fields found:")
        for event_name, common_fields in common_information.items():
            print(f"\t{event_name} with [{','.join(common_fields)}]")

    return common_information


def start(args):
    debug = args.loglevel == logging.DEBUG

    print("Parse report(s)...")
    reports = read_all_the_reports(args.report, args.field_separator, debug)

    print("Analyse found reports...")
    common_information = analyse_reports(reports, debug)

    print("Trying to merge...")
    combined_report = join_sections(reports, common_information, debug)

    write_to_unparser(combined_report, common_information, args)


def main():
    signal.signal(signal.SIGINT, exit_handler)

    parser = ArgumentParser(
        description="Combine information from multiple files (in the best "
                    "case with the same fields).")

    parser.add_argument('-r', '--report',
                        help="Defined report files to be merge.",
                        metavar='N',
                        nargs="+",
                        required=True,
                        type=str)

    parser.add_argument('-o', '--output',
                        help="Name of the merged report file. Default: "
                             "callgraph.report",
                        default="callgraph.report",
                        type=str)

    fine_tuning = parser.add_argument_group("Fine-Tuning")
    fine_tuning.add_argument('-f', '--field-separator',
                             help="Specify the field seperator which was used "
                                  "in the report files and should be used "
                                  "in the final merged file. The field "
                                  "seperator needs to be the same across all "
                                  "report files. "
                                  "Default: $",
                             default='$',
                             dest='field_separator',
                             type=str)

    optional = parser.add_argument_group("Optional")
    optional.add_argument('-d', '--debug',
                          help="Enable debugging statements",
                          action="store_const",
                          dest="loglevel",
                          const=logging.DEBUG)

    args = parser.parse_args()
    start(args)


if __name__ == "__main__":
    main()
