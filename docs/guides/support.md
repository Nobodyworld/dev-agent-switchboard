# Support

Need help with Switchboard? Start with the resources below.

## Self-Service Resources

- [README](../../README.md) — quick start, configuration, and workflow overview.
- [Documentation hub](../index.md) — navigation for API, architecture, configuration, and integration guidance.
- [API Reference](../API.md) — endpoint reference and examples.
- [Configuration Guide](../configuration.md) — environment variables and runtime settings.
- [Automation Guide](automation.md) — guidance for agent and automation integrations.

## Getting Help

If you are blocked or have questions that are not answered in the documentation:

1. Search existing GitHub issues and discussions first.
2. Open a GitHub issue with a minimal reproduction when you have a bug report.
3. Use a question/discussion thread when you need setup or usage guidance.
4. For security-sensitive topics, follow the [Security Policy](../../SECURITY.md) instead of posting details publicly.

Please include:

- operating system and Python version;
- the command you ran;
- relevant configuration values with secrets removed;
- expected behavior;
- actual behavior;
- logs or tracebacks when available.

## Maintainer Response Expectations

Switchboard is maintained as a small open-source/showcase project. Response times are best-effort and depend on maintainer availability.

Recommended expectations:

- Bug reports are triaged when maintainers are available.
- Security reports should use the private disclosure path in [SECURITY.md](../../SECURITY.md).
- Community support is not an operational incident channel.
- There is no on-call pager or guaranteed service-level objective for public users.

## Before Opening an Issue

For setup problems, try:

```bash
python scripts/dev.py --help
python scripts/dev.py verify
pytest -q
```

If a command fails because a local tool is unavailable, include the exact error and the closest command that did run successfully.

Thank you for using Switchboard.