# Releasing the public reference

Build from this repository's reviewed public inputs. Never initialize a release by copying a private research checkout, its generated dashboard, or its Git history.

`PUBLIC_FILES.json` is the exact release file inventory. The release check validates those paths, rejects certain private artifact types, checks common credential patterns, compares the embedded catalog and workspace to their public source files, and compares the tracked file list to the inventory. An edited inventory requires review like an edited program. It is not an automatic content classifier.

Run the tests and build commands in README.md, review the catalog's actual wording, inspect desktop and narrow browser layouts, and examine the staged file list. Check repository history separately. The release script intentionally does not claim to detect every secret, unsafe passage, or historical mistake.

Both `START.html` and `index.html` are generated from the same catalog, web sources, and invented demonstration. They must be byte-identical. The default GitHub Pages deployment uses the root of the public `main` branch with `.nojekyll`; the offline file requires no hosting. The deployed files contain no imported private workspace. See [GitHub's Pages documentation](https://docs.github.com/en/pages/getting-started-with-github-pages/creating-a-github-pages-site).

The CI workflow uses read-only repository permissions, pinned action commits, and no repository secrets. It tests local tools, deterministic output, release inventory, and offline browser behavior. Publishing is a distinct action governed by the owner's instructions.

For a software citation, use CITATION.cff and identify the version or commit. A repository version is not a peer-reviewed validation of the taxonomy or a paper's contribution claims.
