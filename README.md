# hfsort-light

hfsort-light is a collection of tools for:

- [hfsort.py](#hfsort.py): Generating a sorted list of symbols from a report file using a python implementation of the [C3 heuristic from the hhvm/hfsort project](https://github.com/facebook/hhvm/blob/master/hphp/util/hfsort.cpp).
- [similarity.py](#similarity.py): Verifying the correct order of the sorted symbols in the linker script. 
- [hf-merge.py](#hf-merge.py): Merging multiple report files into a single report file.

These tools have been designed for the [objective of reducing ITLB cache pressure through code collocation based on the Linux kernel](https://github.com/antgres/itlb-pressure).

Tested for Python v3.7.3.

## hfsort.py

Uses the C3 heuristic to sort a report list, which is generated via *perf record* and *perf report*. See [here](https://github.com/antgres/itlb-pressure) for more information. Example files can be found and used in the folder *test-data*. In its simplest form *hfsort.py* can be used via

    python hfsort.py --report test-data/callgraph.report

which outputs a sorted list in the *sorted* file from the given report file. Additional flags can be used to generate more information.

A report file is at the minimum defined by the fields *Samples*, *Source symbol*, and *Target symbol*, which correspond to the perf report flags '--sort samples --fields +symbol_from,symbol_to'. Additional information such as the symbol size can be provided using the perf report flag '--fields +symbol_size' or the built-in flags *-k* or *-S*.

To use [similarity.py](#similarity.py), the debug flag *-d* needs to be included.

Additional flags can be:

- -r --report
   : Report file with observed samples for every caller-callee call.

- -l --linker-script
   : Output the sorted list in a simple linker script format.

- -t \--template
   : Integrate the sorted list into a vmlinux.lds.template file.

- -f --field-separator
   : Specify the field separator used in the report file. 
   [Default: $]

- -p --min-probability
   : Set the minimum probability for an arc to be relevant. The
   weight of an arc is calculated via its own number of samples
   divided by the total amount of samples.
   [Default: 0.1]

- -P --page-size
   : Set the page size according to which the C3 heuristic sets the
   maximum cluster size.
   [Default: 4096 [byte]]

- -k --kallsyms
   : Use the output from /proc/kallsyms to calculate the symbol sizes
   from. However, it provides only an upper bound for the symbol
   size and is therefore not bit precise.

- -S --sizefile
   : Use the information of a file to lookup the bit precise symbol
   size. The file can be created via the example command
   'nm -S vmlinux > sizefile'.

- -v --verbose
   : Enable verbose statements.

- -d --debug
    : Enable debugging statements and debugging information in files.

## similarity.py

Check the generated ideal function layout generated from *hfsort.py* against a real compiled function layout from the final ELF file. The real function layout of the kernel can be obtained from *System.map* file or the output of */proc/kallsyms*. The following tests are then carried out:

- *Similarity test*: Check for missing functions in the real function layout which occur in the ideal function layout.
- *Out-of-Order test*: Check if functions are not in the ideal order. For this test the assumption is made that if a function is not already placed by the linker in a previous command then it should also appear in the correct order. 
- *Final ranking test*: Since missing functions are automatically counted as out-of-order functions, subtract the missing functions from the out-of-order functions to get the real number of out-of-order functions. 

In its simplest form *similarity.py* can be used via

    python similarity.py --sorted-file sorted --system-map System.map

The flags *--kallsyms* and *--system-map* can't be used together.

Additional flags can be:

- -i --sorted-file
   : Original sorted layout file as reference.

- -I --system-map
   : Use a System.map file to check against.

- -k --kallsyms
   : Use the output from /proc/kallsyms to check against the running
   kernel.

- -S --start-symbol
   : Define the symbol in the symbol file that marks the beginning of
   the custom layout in the text section.
   [Default: __hfsort_start]

- -e --end-symbol
   : Define the end symbol in the symbol file that marks the end of
   the custom layout in the text section.
   [Default: __hfsort_end]

- -d --debug
   : Generate debugging statements. Additionally, files are generated
   that show detailed information based on the tested property.

## hf-merge.py

Based on the idea of [llvm-profdata merge](https://llvm.org/docs/CommandGuide/llvm-profdata.html#profdata-merge).

*hf-merge.py* tries to merge multiple *callgraph-*.report* files into a single *callgraph.report*. When a generated *perf.data* file is too big to save without losing chunks, merging smaller report files can provide a more precise weighted call graph.

A report files must have at least the following fields: Samples, Source Symbol, Target Symbol.

The basic usage of *hf-merge.py* is:

    python hf-merge.py --report 1-callgraph.report 2-callgraph.report
    python hfsort.py --report callgraph.report

Additional flags can be:

- -r --report
   : Report files to be merged.

- -o --output
   : Name of the report file which has the merged information.
   [Default: callgraph.report]

- -f --field-separator
   : Specify the field seperator which was used in the report files
   and should be used in the final merged file. The field seperator
   needs to be the same across all report files.
   [Default: $]

- -d --debug
   : Enable debugging statements.
