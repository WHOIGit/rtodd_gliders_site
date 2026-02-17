# This script converts a BibTeX file to an HTML file
# using Pandoc and a custom reformatting script.

# Path of this script
SCRIPTROOT=$(dirname "$(realpath "$0")")

# Input: A BibTeX file specified as the first argument.
INPUTBIB=$(realpath "$1")

# Output: An HTML file generated from the BibTeX file.
OUTPUTHTML=${2:-"$SCRIPTROOT/output/publications.html"}
echo "$OUTPUTHTML"

# pandoc is a program that can convert between various document formats
#   frontmatter.md is a markdown file,
#   nocite: '@*' specifies to not exclude any bib entries
pandoc "$SCRIPTROOT/frontmatter.md" --bibliography="$INPUTBIB" --csl="$SCRIPTROOT/american-geophysical-union.csl" -o "$OUTPUTHTML"

# reformat.py is a custom Python script that further processes the generated HTML file
#  (1) groups entries by year applies
#  (2) neatens the he doi links
#  (3) Bolds
python3 "$SCRIPTROOT/reformat.py" "$OUTPUTHTML" --bold "$SCRIPTROOT/input/bold_authors.txt" --rm-html-body -o "$OUTPUTHTML"


