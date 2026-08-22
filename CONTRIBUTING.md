# Contributing to dn42-mmdb

Thank you for contributing to `dn42-mmdb`.

## Developer Certificate of Origin (DCO)

All commits must include a `Signed-off-by` trailer certifying the Developer Certificate of Origin (DCO).
Generate this trailer automatically using `git commit -s`:

```text
Signed-off-by: Your Name <your.email@example.com>
```

## AI Contribution Policy

Contributions created with assistance from AI tools are welcome.
Commits containing AI-generated or AI-assisted content must carry an `Assisted-by` trailer before the `Signed-off-by` trailer:

```text
Assisted-by: Antigravity:gemini-3.6-flash
Signed-off-by: Your Name <your.email@example.com>
```

The human submitter signing off the commit remains fully responsible for review, correctness, and license compliance.

## Workflow

1. Open a GitHub issue describing the bug or feature before submitting a Pull Request.
2. Ensure `make verify` passes cleanly.
3. Submit your Pull Request referencing the issue using `Closes #<issue-number>`.

## Getting a registry checkout

Building the databases needs a checkout of the [dn42 registry](https://git.dn42.dev/dn42/registry).
`git.dn42.dev` requires an account and has no anonymous route: the git endpoints answer `401`, and `/archive/master.tar.gz` answers `200` with a sign-in page rather than an archive.

Note that `make verify` needs no registry at all, so most contributions require none of this.

### In your own fork's CI

The release workflow resolves the registry URL in this order:

1. the `registry_url` input, when you start the workflow manually
2. the `DN42_REGISTRY_URL` secret
3. the `DN42_REGISTRY_URL` repository variable
4. `https://git.dn42.dev/dn42/registry.git`

Configure either a `DN42_REGISTRY_TOKEN` secret holding a git.dn42.dev access token, or a `DN42_REGISTRY_URL` variable naming a registry mirror you trust.
With neither set, the clone step fails immediately and tells you both options rather than letting git fail on a credential prompt.

### Geofeed coverage in a fork

The registry declares 39 geofeed URLs, and 22 of them are on `.dn42` hostnames that are unreachable from the public internet.

The upstream sync workflow reaches them by joining the maintainer's tailnet as an ephemeral node, routed to dn42 through a peer acting as a subnet router.
That needs `TS_OAUTH_CLIENT_ID` and `TS_OAUTH_CLIENT_SECRET`, which a fork will not have, so the step is skipped and the sync collects the clearnet-reachable feeds only.

This is expected, not a failure.
Rows from feeds that could not be reached are retained from the committed snapshot rather than dropped, so a fork's sync narrows coverage instead of destroying it.
The same applies upstream whenever the peer is down.

### Mirrors must be non-commercial

The registry's own README states:

> You **must not** clone or mirror the registry in to a commercial git repository; commercial terms of service can be incompatible with the use of personal data in the registry.

The registry holds dn42 members' personal information, and whoever copies it is expected to honour update and deletion requests.
Mirrors hosted on commercial git platforms are therefore out, and this project does not name a mirror to point you at.
Choosing one is your decision for your own fork.

This project's own CI clone is compatible with that restriction: it is shallow, exists only in an ephemeral runner filesystem, is never pushed anywhere, and is destroyed when the job ends.
