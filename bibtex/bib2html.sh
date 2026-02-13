# This script converts a BibTeX file to an HTML file
# using Pandoc and a custom reformatting script.

# Input: A BibTeX file specified as the first argument.
INPUTBIB="$1"

# Output: An HTML file generated from the BibTeX file.
OUTPUTHTML="output/publications.html"

# pandoc is a program that can convert between various document formats
#   frontmatter.md is a markdown file that specifies the citation style
pandoc frontmatter.md --bibliography="$INPUTBIB" -o "$OUTPUTHTML"

# reformat.py is a custom Python script that further processes the generated HTML file
#  (1) groups entries by year applies
#  (2) neatens the he doi links
#  (3) Bolds
python3 reformat.py "$OUTPUTHTML" --bold "input/bold_authors.txt" --rm-html-body -o "$OUTPUTHTML"

