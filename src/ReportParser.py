from io import StringIO

from src.common.classes import Metadata, Section
from src.common.functions import find_common_items_in_list


class PerfReportParser:
    """
    Parse the created report file into usable information.

    Attributes:
        field_separator: Field separator used in the report file. Cut the text
        line into values accordingly.
        header_section: Flag indicating whether the parser is in the header
        section.
        walked_sections: Number of sections walked.
        metadata: Parsed metadata information (Additional information from the
        report file).
        section: Parsed section information. A section is defined by its event.
        start_fields: Flag indicating whether the parser is at the start of
        the fields.
    """

    def __init__(self, field_separator):
        self.field_separator = field_separator
        self.header_section = False
        self.walked_sections = 0
        self.metadata = Metadata()
        self.section = Section()
        self.start_fields = False

    def _convert(self, value):
        """
        Convert the value into a usable format depending on the given
        information in the value. Value is always of type str.
        """

        if '%' in value:
            return float(value.replace('%', ''))
        if ':' in value:
            return value.replace(':', '_')
        if '[' and ']' in value:
            return value.split(" ")[-1]
        if ' ' in value:
            return value.replace(' ', '_')
        if value.isdigit():
            return int(value)
        if "unknown" in value:
            return 0

        return value

    def _split_and_clean_values(self, line):
        """
        Split the line depending on the field separator and then convert
        the lower string value depending on its value into a usable value.
        """
        return [self._convert(split.strip().lower())
                for split in line.split(self.field_separator)]

    def _parse_comments(self, line):
        """Parse the comments depending on specific cues."""
        if not line:
            # if the line is empty it is a spacer
            return

        if '========' in line:
            # if the given chars are found we are in the metadata section
            # so declare the start of the only metadata  section
            self.header_section = not self.header_section
            return

        # if we are in the metadata section save the information
        # append the information to metadata
        if self.header_section:
            # strip possible left whitespace before appending
            self.metadata.header_information += [line.lstrip()]
            return

        if "Total Lost Samples" in line:
            # Section information: '# Total Lost Samples: 0'
            self.section.header.update({"lost": line.split()[-1]})
            return
        if "of event" in line:
            # Section information: "# Samples: 40M of event 'cycles:k'"
            self.section.header.update({"event_name": line.split("\'")[-2]})
            return

        # 'Event counts' needs to be checked after start_fields because
        # else the boolean start_fields get messed up because of the
        # particular order in the file.
        if self.start_fields:
            self.section.fields = self._split_and_clean_values(line)
            self.start_fields = False
            return
        if "Event count" in line:
            # Section information: '# Event count (approx.): 40632332'
            self.section.header.update({"total_samples": line.split()[-1]})
            self.start_fields = True
            return

    def parse(self, raw_text_generator):
        if not raw_text_generator:
            return None

        new_section = False

        for line in raw_text_generator:
            if line.startswith('#'):
                if new_section:
                    # if a new section starts append the saved
                    # section to metadata
                    self.metadata.sections += [self.section]

                    self.section = Section()
                    self.walked_sections += 1
                    new_section = False

                line = line.lstrip('#').strip()
                self._parse_comments(line)
                continue

            # if not comment section its data section
            if not new_section:
                new_section = True

            if not line:
                # empty spacer
                continue

            data_line = {
                field: value
                for value, field in zip(
                    self._split_and_clean_values(line),
                    self.section.fields,
                )
            }

            self.section.values += [data_line]

        return self.metadata

    def clean_parser(self):
        """
        Clean the saved values from the previous run to be able to
        continue with a new parser run.
        """
        self.header_section = False
        self.walked_sections = 0
        self.metadata = Metadata()
        self.section = Section()
        self.start_fields = False


class PerfReportUnparser:
    """
    Unparse a report information back into a file.

    Attributes:
        field_separator: Field separator used in the report file. Cut the text
        line into values accordingly.
        common_fields: Ordered column names by which the values should be
        sorted.

    """

    def __init__(self, field_separator, common_fields):
        self.field_separator = field_separator
        self.common_fields = self._ordered_fields(common_fields)

    def _ordered_fields(self, fields):
        """
        Enforce a specific order of the fields in the final report file.
        Start with the ordered fields defined in ordered_fields and append
        every other field found after that.
        """
        ordered_fields = ["samples", "source_symbol", "target_symbol"]

        common_items = find_common_items_in_list(fields.values())

        difference = list(set(common_items) - set(ordered_fields))
        if difference: difference.sort()

        return tuple(ordered_fields + difference)

    def _create_fields(self):
        """
        Create the column (fields) line for a section. Change the field names
        from, for example, 'target_symbol' to 'Target symbol'.
        """
        fields = [field.replace("_", " ").capitalize()
                  for field in self.common_fields]

        return """# {fields}
""".format(
            fields=f"\t{self.field_separator}".join(fields)
        )

    def _create_section_values(self, values):
        """
        Create the value lines for a section. Sort the values according to
        their samples.
        """

        sorted_values = sorted(values, key=lambda d: d["samples"], reverse=True)
        text = StringIO()

        for value in sorted_values:
            value_order = f"\t{self.field_separator}\t".join(
                [str(value.get(field)) for field in self.common_fields]
            )
            text.write(f" {value_order}\n")

        return text.getvalue()

    def _calculate_prefix(self, value):
        """
        Calculate the needed prefix for a value. For example the value
        51947858 should be abbreviated as 51M.
         """
        characters, value = len(str(value)), int(value)

        if value < 0 or value > 10 ** 17:
            return "NULL"

        si_prefixes = ['', 'K', 'M', 'G', 'T', 'P']
        suffix_index = max(0, min(characters // 3, len(si_prefixes) - 1))
        divisor = 1000 ** suffix_index

        return f"{int(value // divisor)}{si_prefixes[suffix_index]}"

    def _create_section_header(self, header):
        """Create the header lines for a section."""

        total_samples = header.get("total_samples")

        return """#
# Total Lost Samples: {lost_samples}
#
# Samples: {approx_total_value} of event '{section_name}'
# Event count (approx.): {total_samples}
#
""".format(
            lost_samples=header.get("lost"),
            approx_total_value=self._calculate_prefix(total_samples),
            section_name=header.get("event_name"),
            total_samples=total_samples
        )

    def unparse(self, metadata):
        whole_text, total_sections = StringIO(), len(metadata.sections)

        for index, section in enumerate(metadata.sections):
            whole_text.write(self._create_section_header(section.header))
            whole_text.write(self._create_fields())
            whole_text.write(
                self._create_section_values(section.values)
            )

            whole_text.write("\n\n")

            if index == total_sections - 1:
                whole_text.write(
                    "# Do not delete this comment symbol or else the parser "
                    "is very confused."
                )

        return whole_text.getvalue()
