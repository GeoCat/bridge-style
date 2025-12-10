# Publishing on PyPI

If you wish to release a new package for [PyPI](https://pypi.org/), you can use [Zest Releaser](https://pypi.org/project/zest-releaser/).

Once you have Zest Releaser installed, you can follow these steps to publish the project:

1. First write release notes in the `CHANGES.md` file below the version where it says `(unreleased)`.
2. Now open a terminal and activate your virtual environment if necessary.
3. Run `fullrelease` in the command line.
4. Follow the prompts (version number, etc.) to create a new release.
   The defaults are generally good, but you can customize them if needed.
5. The tool will update `version.py` and `CHANGES.md` with the new version number.
6. It will also create release commits and a tag for the new release.
7. Push the changes to GitHub, confirming each step as prompted.
8. Once the tag is pushed to GitHub, the [GH Action](/.github/workflows/release.yml) will automatically build and release the package to PyPI.
