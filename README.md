# 轻读 QingDu - HSK Chinese Text Analyzer

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

A modern web application for analyzing Chinese text difficulty based on HSK (Hanyu Shuiping Kaoshi) vocabulary levels. Paste any Chinese text and instantly see which words you should know at each HSK level, with automatic pinyin, translations, and difficulty highlighting.

## Features

- **HSK-based Analysis** - Analyze texts with 11,000+ words from HSK 1-9
- **Visual Difficulty Highlighting** - Color-coded words by HSK level
- **Smart Pinyin Display** - Automatic pinyin for words above your reading level
- **Interactive Learning** - Click words for definitions, sentences for translations
- **Text-to-Speech** - Hear native pronunciation
- **Vocabulary Lists** - Generate HSK level lists or create custom study lists
- **Save & Track** - Save texts for later review with user accounts
- **Invitation System** - Controlled user registration with admin management

## Quick Start

### Using Docker (Recommended)

```bash
git clone https://github.com/mkampl/qingdu.git
cd qingdu
docker compose up -d --build
```

Access the app at `http://localhost:8000`.

On first boot, a random admin password is generated and written to
`./data/admin_bootstrap.txt` (mode 0600) plus printed loudly to the startup
logs. The user is forced to change it on first login.

For local development with hot-reload + the Vite dev server on `:5173`, layer
the dev compose file:

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml up
```

### Contributing

Install pre-commit hooks so your local edits match what CI gates on:

```bash
pip install pre-commit && pre-commit install
```

See [SETUP.md](SETUP.md) for detailed setup instructions including optional API keys for better translation quality.

## Documentation

- **[Features Guide](FEATURES.md)** - Detailed feature descriptions and usage
- **[API Documentation](API.md)** - Complete API endpoint reference
- **[Contributing Guide](CONTRIBUTING.md)** - Development setup and guidelines
- **[Setup Guide](SETUP.md)** - Detailed installation and configuration

## Technology Stack

Built with **FastAPI** (Python), **jieba** (Chinese segmentation), **pypinyin** (Pinyin conversion), and **vanilla JavaScript**. Uses SQLite for data persistence and supports optional DeepL/Google Translate APIs.

## Screenshots

![Text Analysis](docs/screenshots/analysis.png)
_HSK-based text analysis with color-coded difficulty levels_

![Vocabulary Lists](docs/screenshots/vocab-lists.png)
_Generate and manage vocabulary study lists_

## Contributing

Contributions welcome! Please read [CONTRIBUTING.md](CONTRIBUTING.md) for development setup and guidelines.

Ideas for contributions:
- Additional language pairs for translation
- Anki/CSV export for vocabulary lists
- Dark mode theme
- Spaced repetition system (SRS)

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

Third-party licenses and attributions: [THIRD_PARTY_LICENSES.md](THIRD_PARTY_LICENSES.md)

## Credits

- **HSK Vocabulary**: [drkameleon/complete-hsk-vocabulary](https://github.com/drkameleon/complete-hsk-vocabulary) (MIT)
- **Chinese Segmentation**: [jieba](https://github.com/fxsjy/jieba) (MIT)
- **Pinyin Conversion**: [pypinyin](https://github.com/mozillazg/python-pinyin) (MIT)

See [THIRD_PARTY_LICENSES.md](THIRD_PARTY_LICENSES.md) for complete dependency list.

## Support

- [Open an issue](https://github.com/mkampl/qingdu/issues) for bug reports or feature requests
- [Ko-fi](https://ko-fi.com/mkampl) - Support the project

---

Made with ❤️ for Chinese language learners
