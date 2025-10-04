# 轻读 QingDu - HSK Chinese Text Analyzer

A modern web application for analyzing Chinese text difficulty based on HSK (Hanyu Shuiping Kaoshi) vocabulary levels.

## Features

### Text Analysis
- **HSK-based vocabulary analysis** with 11,000+ words from HSK 1-9
- **Visual difficulty highlighting** - each word is color-coded by HSK level
- **Automatic pinyin display** for words above your estimated reading level
- **Smart text segmentation** using jieba with HSK word prioritization
- **Reading level estimation** based on word distribution

### Learning Tools
- **Word information panel** - click any word to see pinyin, meaning, and HSK level
- **Sentence translations** - click sentences for instant translation
- **Text-to-speech** - hear pronunciation for words and sentences
- **Save texts** for later review with persistent storage
- **Vocabulary lists** - generate HSK level lists or create custom study lists

### Translation Services
- Multiple API support (priority: DeepL → Google → MyMemory)
- Smart caching to reduce API calls
- Fallback to free services when API keys not provided

## Quick Start

### Using Docker (Recommended)

1. **Clone the repository:**
   ```bash
   git clone <your-repo-url>
   cd qingdu
   ```

2. **Start the application:**
   ```bash
   docker-compose up -d
   ```

3. **Access the app:**
   Open your browser to `http://localhost:8000`

### Manual Setup

1. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

2. **Run the application:**
   ```bash
   python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
   ```

## Configuration

### Optional API Keys

For better translation quality, add API keys to `.env` file:

```env
# DeepL API (best quality)
DEEPL_API_KEY=your_deepl_api_key

# Google Translate API (good quality)
GOOGLE_TRANSLATE_API_KEY=your_google_api_key
```

**Note:** If no API keys are provided, the app uses the free MyMemory API.

### Environment Variables

```env
LOG_LEVEL=info
PYTHONUNBUFFERED=1
```


## Technology Stack

### Backend
- **FastAPI** - Modern Python web framework
- **jieba** - Chinese text segmentation
- **pypinyin** - Pinyin conversion
- **SQLAlchemy** - Database ORM
- **httpx** - Async HTTP client

### Frontend
- **Vanilla JavaScript** (ES6+) - No frameworks needed
- **Modern CSS** - Responsive design with flexbox/grid
- **LocalStorage** - Client-side data persistence

### Infrastructure
- **Docker** - Containerization
- **SQLite** - Embedded database
- **Uvicorn** - ASGI server

## API Endpoints

### Analysis
- `POST /api/analyze` - Analyze Chinese text
- `POST /api/translate` - Translate text
- `GET /api/tts/{text}` - Text-to-speech

### Data Management
- `GET /api/texts` - Get saved texts
- `POST /api/texts/save` - Save analyzed text
- `DELETE /api/texts/{id}` - Delete text

### Vocabulary
- `GET /api/vocabulary-stats` - Get vocabulary statistics
- `GET /api/get-hsk-vocabulary` - Get complete HSK vocabulary

## Features in Detail

### HSK Level Colors

- **HSK 1** - Light green
- **HSK 2** - Light blue
- **HSK 3** - Light orange
- **HSK 4** - Light pink
- **HSK 5** - Light purple
- **HSK 6** - Light red
- **HSK 7-9** - Various earth tones
- **Unknown** - Gray (requires online lookup)

### Text Interactions

- **Click word** - View definition, pinyin, and HSK level
- **Click sentence** - Get translation with source attribution
- **Long-press sentence** - Same as click (mobile-friendly)
- **Save word** - Add to vocabulary list for the current text

## Development

### Local Development

1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

2. Run with auto-reload:
   ```bash
   uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
   ```

### Code Quality

The codebase follows modern JavaScript practices:
- ES6+ syntax (const/let, arrow functions, template literals)
- Modular organization (separate files for different concerns)
- Async/await for asynchronous operations
- Error handling with try/catch

## Performance Optimizations

- **LRU caching** for word lookups
- **Translation caching** to minimize API calls
- **Rate limiting** on API endpoints (30/min for analyze, 20/min for translate)
- **Efficient text segmentation** with jieba
- **Lazy loading** of HSK vocabulary


## Contributing

Contributions are welcome! Areas for improvement:
- Additional language pairs for translation
- Anki/CSV export for vocabulary lists
- Dark mode
- PWA (Progressive Web App) support
- Spaced repetition system (SRS)

## License

MIT License - feel free to use and modify as needed.

## Credits

- HSK Vocabulary data: [drkameleon/complete-hsk-vocabulary](https://github.com/drkameleon/complete-hsk-vocabulary)
- Chinese segmentation: [jieba](https://github.com/fxsjy/jieba)
- Pinyin conversion: [pypinyin](https://github.com/mozillazg/python-pinyin)

## Support

For issues, questions, or suggestions:
- Open an issue on GitHub
- Check existing documentation
- Review the code comments

---

Made with ❤️ for Chinese language learners