# Contributing to `bridgestyle`

Would you like to add or fix something? Great! Taking part is the only way open source works for everyone! 😊

By making a contribution you understand that:

* *bridge-style* is open source, distributed with an [MIT License](/LICENSE.md).
* Library documentation is also open, distributed with a [Creative Commons Attribution License](https://creativecommons.org/licenses/by/4.0/).
* This project uses a pull request (PR) workflow to review and accept changes. Pull requests should be submitted against the `master` branch.
* Contributions provided by you (or on behalf of your employer) are required to be compatible with this free-software license. You will therefore be asked to sign the [Contributor License Agreement](https://cla-assistant.io/geocat/bridge-style) when you are contributing to the repository. This process is automatically enabled when you create your first pull request (PR).

[![CLA assistant](https://cla-assistant.io/readme/badge/geocat/bridge-style)](https://cla-assistant.io/geocat/bridge-style)

## Guidelines

### Release Notes

We would like to thank you for your work in the [release notes](/CHANGES.md).

The project maintainers will update the release notes when a new release comes out. We kindly ask you to provide detailed information about your contribution in your PR (pull request) or a related issue, so we can use that information to update the release notes.

### Commits

You are encouraged to add elaborate commit descriptions, targeting a developer audience:

✅ `MapBox Style line-offset skipped for None (and default of 0)`
❌ `mapbox style fixes`

Keep your commits small and preferably focused on a single change. This makes it easier to review and understand the changes you made.
For larger contributions, try to squash logical "units of work" into individual commits. This helps maintain a clean commit history and makes it easier to track changes over time.

In this project, we like to keep a linear commit history, so please avoid using merge commits if possible.  
Instead, use `git rebase` to keep your branch up to date with the main branch before submitting your PR.

### Pull Requests

When you create a pull request (PR), please make sure to:
* Provide a clear description of the changes you made and what the purpose is.
* Link to any related issues or discussions.

You may only omit a description from the PR if it's the result of a discussion or issue. In that case, you are required to link it to the PR.

### Bug Fixes

There currently aren't any automated unit tests (😥), but in the future we would like to see bug fixes covered by a test case:

* Often you can quickly add another check to an existing test-case.
* When including test data, be sure to remove sensitive information.

If you would like to start writing unit tests, please check the [tests folder](/tests) for examples. 
The tests are written in Python and use the `unittest` framework.

### Features

If you are contributing a new feature or I/O format, please add *any* documentation describing your change (either in the PR/issue and/or the [docs folder](/docs)):

* Quickly adding an example to an existing page works well for existing formats.
* Feel free to make a new page when adding an output format or capability.

Because this is a cartographic library, visual examples are encouraged.
