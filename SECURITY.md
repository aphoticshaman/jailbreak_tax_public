# Security and data handling

The browser page runs locally and needs no network access. It uses no remote assets, model endpoint, telemetry, or API key. Clicking a source link opens the external source in your browser.

The local tools treat logs as untrusted data. They import metadata into a separate private directory, preserve original files, and do not execute imported content. Research pages and assistant handoffs can contain sensitive metadata even when transcripts are omitted. Keep them private.

Public generation uses fixed public inputs and an invented example. It does not discover working directories. Private directories must not overlap the public repository. Git ignore patterns and release checks provide additional protection; neither replaces review of the actual files being published. Changes to ignore patterns cannot remove information already committed to Git history.

To report a vulnerability, use this repository's private vulnerability reporting feature if available. Do not put credentials, personal research, or operational attack material in a public issue. A public issue is suitable for an ordinary UI bug demonstrated with invented data.

Security tests cover specific failure modes, including path isolation, data validation, literal rendering, and offline operation. They are not a security certification. The tool cannot determine whether an arbitrary imported statement is true or whether every possible secret has been removed from a manually edited file.
