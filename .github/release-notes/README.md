# Release highlights

To prepend an announcement to GitHub's generated changelog, add a Markdown file
whose name exactly matches the release tag, for example `1.15.0.md` for tag
`1.15.0` or `1.15.0b1.md` for tag `1.15.0b1`.

Merge the file before pushing the tag. The release workflow reads the file from
the tagged commit and prepends it to the automatically generated release notes.
Tags without a matching file use generated notes only. Existing highlights can
remain here; they are only included for their matching tag.
