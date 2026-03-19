# Contributing to youtube-utils

Thanks for your interest in contributing!

## Getting Started

1. Fork the repo and clone your fork
2. Run `bash scripts/setup.sh` to set up the environment
3. Copy `.env.example` to `.env` and fill in your API keys

## Development

```bash
# Lint
ruff check src/

# Format
ruff format src/

# Run pre-commit hooks locally
pre-commit run --all-files
```

## Areas for Contribution

- **New LLM backends**: Add support for additional providers (e.g., Gemini, Claude, Ollama)
- **Language support**: Extend subtitle/summary languages beyond zh-TW and English
- **Quality checks**: Add new QC rules for summary verification
- **Export formats**: Add new output formats beyond HTML/PDF
- **Tests**: Add unit/integration tests for core functions

## Pull Request Guidelines

1. Create a feature branch from `main`
2. Keep changes focused — one feature or fix per PR
3. Ensure `ruff check` and `ruff format --check` pass
4. Update README if adding user-facing features
5. Use clear, descriptive commit messages

## Reporting Issues

Open a GitHub issue with:
- What you expected vs what happened
- Steps to reproduce
- Python version and OS
- Relevant error output

## License

By contributing, you agree that your contributions will be licensed under the MIT License.
