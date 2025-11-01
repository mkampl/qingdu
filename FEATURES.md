# QingDu Features Guide

Complete guide to all features available in QingDu Chinese Text Analyzer.

## Table of Contents

- [Text Analysis](#text-analysis)
- [HSK Level System](#hsk-level-system)
- [Interactive Learning](#interactive-learning)
- [Vocabulary Management](#vocabulary-management)
- [Text Management](#text-management)
- [User System](#user-system)
- [Translation Services](#translation-services)
- [Settings](#settings)

---

## Text Analysis

### Paste and Analyze

Simply paste any Chinese text into the input area and click "Analyze Text". QingDu will:

1. **Segment the text** using jieba with HSK word prioritization
2. **Identify HSK levels** for each word from a database of 11,000+ words
3. **Estimate your reading level** based on word distribution
4. **Generate automatic pinyin** for words above your estimated level
5. **Provide visual highlighting** with color-coded difficulty

### Smart Segmentation

QingDu uses jieba for text segmentation with special enhancements:

- **HSK word prioritization** - Multi-character HSK words are recognized correctly
- **Line break preservation** - Original text formatting is maintained
- **Punctuation handling** - Chinese and English punctuation handled appropriately

### Reading Level Estimation

The app estimates your reading level based on the text's word distribution:

- Analyzes the percentage of words at each HSK level
- Suggests an appropriate reading level
- Shows statistics for each HSK level present in the text

---

## HSK Level System

### HSK Level Colors

Words are color-coded by their HSK level for quick visual reference:

| HSK Level | Color | Description |
|-----------|-------|-------------|
| **HSK 1** | Light Green (#c8e6c9) | Beginner - 150 words |
| **HSK 2** | Light Blue (#b3e5fc) | Elementary - 300 words |
| **HSK 3** | Light Orange (#ffe0b2) | Pre-intermediate - 600 words |
| **HSK 4** | Light Pink (#f8bbd0) | Intermediate - 1,200 words |
| **HSK 5** | Light Purple (#e1bee7) | Upper intermediate - 2,500 words |
| **HSK 6** | Light Red (#ffcdd2) | Advanced - 5,000 words |
| **HSK 7** | Tan (#d7ccc8) | Superior - 3,000 words |
| **HSK 8** | Light Olive (#e6ee9c) | Expert - 3,000 words |
| **HSK 9** | Beige (#f0f4c3) | Master - 3,000 words |
| **Unknown** | Gray (#e0e0e0) | Not in HSK list |

### HSK Vocabulary Database

- **11,247 words** covering HSK 1-9
- Each word includes:
  - Traditional and simplified characters
  - Pinyin with tone marks
  - English definitions (multiple meanings)
  - HSK level classification
  - Frequency data

### Visual Indicators

- **Word highlighting** - Hover to see the word emphasized
- **Pinyin display** - Automatic for words above your level
- **Level badges** - Click words to see detailed HSK level info

---

## Interactive Learning

### Word Information Panel

Click any word to see detailed information:

- **Chinese character** - The word in context
- **Pinyin** - With tone marks (e.g., "nǐ hǎo")
- **English meaning** - Primary definition
- **Multiple meanings** - All possible translations
- **HSK Level** - Which HSK level the word belongs to
- **Frequency** - Usage frequency (1-9 scale)

### Sentence Translation

Click any sentence (or long-press on mobile) to:

- **Get instant translation** - English translation of the full sentence
- **See translation source** - Know if it's from DeepL, Google, or MyMemory
- **Understand context** - See how words work together

### Text-to-Speech

Hear correct pronunciation:

- **Click the speaker icon** next to any word
- **Listen to sentences** - Full sentence pronunciation
- **Native pronunciation** - Uses Google Text-to-Speech
- **Tone accuracy** - Proper tones for learning

### Add to Vocabulary List

While reading:

- **Click "Add to List"** to save interesting words
- **Organize by text** - Each saved text has its own vocabulary list
- **Study later** - Review vocabulary without the full text

---

## Vocabulary Management

### Vocabulary Lists

Create and manage custom study lists:

- **HSK Level Lists** - Generate lists filtered by HSK level
- **Custom Lists** - Create lists with any words you choose
- **List Sections** - Organize words by HSK level within lists
- **Permission System** - Mark sections as locked or unlocked

### Adding Words

Three ways to add words to lists:

1. **From text analysis** - Click "Add to List" while reading
2. **Manual entry** - Type words directly into a list
3. **Import** - Generate HSK level vocabulary lists

### Managing Lists

- **Edit list names** - Rename lists anytime
- **Delete lists** - Remove lists you no longer need
- **Add/remove words** - Full control over list content
- **Move words** - Reorganize within lists

### Word Details in Lists

Each word in a list shows:

- Chinese characters
- Pinyin (auto-generated if not provided)
- English meaning
- HSK level
- Custom notes (coming soon)

### Exporting (Coming Soon)

- Anki deck export (.apkg)
- CSV export for spreadsheets
- Print-friendly format

---

## Text Management

### Saving Texts

Save analyzed texts for later review:

- **Auto-save analysis** - All analysis data preserved
- **Add titles** - Name your texts for easy reference
- **Tag texts** - Organize with custom tags
- **Track progress** - Mark reading progress (0-100%)

### Viewing Saved Texts

- **List view** - See all saved texts at a glance
- **Search/filter** - Find texts by title or tag
- **Sort options** - By date, title, or progress
- **Quick access** - Click to load full analysis

### Editing Texts

- **Edit content** - Update the Chinese text
- **Reanalyze** - Run analysis again after edits
- **Update tags** - Change organization
- **Edit titles** - Rename for clarity

### Reading Progress

Track how far you've read:

- **Progress bar** - Visual indicator of completion
- **Percentage** - Exact reading progress (0-100%)
- **Auto-save** - Progress saved automatically
- **Resume reading** - Pick up where you left off

### Deleting Texts

- **Confirm deletion** - Prevents accidental removal
- **Cascade delete** - Associated vocabulary lists also deleted
- **Permanent** - Cannot be undone

---

## User System

### User Accounts

- **Secure authentication** - JWT-based login system
- **Password requirements** - Minimum 8 characters
- **Session management** - Stay logged in across sessions
- **Password change** - Change password anytime

### Invitation System

New user registration is controlled:

- **Invitation-only** - Users need an invitation link to sign up
- **Invitation quota** - Each user has a limited number of invitations
- **Admin control** - Admins can adjust quotas
- **30-day expiration** - Invitation links expire after 30 days

### Generating Invitations

As a user, you can:

1. **Check your quota** - See how many invitations you have
2. **Generate link** - Create a unique invitation URL
3. **Share the link** - Send to friends who want to join
4. **Track usage** - See which invitations were claimed

### User Settings

- **Change password** - Update your password
- **View profile** - See your username and admin status
- **Manage invitations** - View and generate invitation links
- **Logout** - End your session

---

## Admin Features

### User Management

Admins can:

- **View all users** - See complete user list
- **Create users** - Add users directly (without invitation)
- **Reset passwords** - Help users who forgot passwords
- **Toggle admin status** - Promote/demote administrators
- **Update invite quotas** - Control who can invite others
- **Delete users** - Remove user accounts and all their data

### Admin Panel

Access at `/admin` (admins only):

- **User table** - Sortable list of all users
- **Inline editing** - Edit invite quotas directly
- **Quick actions** - Reset password, delete, toggle admin
- **Creation date** - When users joined
- **Last active** - When users last logged in

---

## Translation Services

### Multi-API Support

QingDu supports multiple translation APIs with fallback:

1. **DeepL** (Best quality) - If API key provided
2. **Google Translate** (Good quality) - If API key provided
3. **MyMemory** (Free, decent quality) - Always available as fallback

### Translation Caching

- **Smart caching** - Repeated translations returned instantly
- **Reduced API calls** - Save on API costs
- **Faster responses** - Instant for cached translations

### Source Attribution

Every translation shows its source:

- "Translated by DeepL"
- "Translated by Google Translate"
- "Translated by MyMemory"

---

## Settings

### Pinyin Display Modes

Choose how pinyin is displayed:

- **Auto (default)** - Show pinyin for words above your estimated level
- **On** - Always show pinyin for all words
- **Off** - Never show pinyin

Settings are saved in your browser (localStorage) and work without login.

### User Interface

- **Responsive design** - Works on desktop, tablet, and mobile
- **Mobile-friendly** - Touch-optimized interactions
- **Loading indicators** - Clear feedback during analysis
- **Progress bars** - Visual progress for long operations

### Browser Settings

The following settings are saved in your browser:

- Pinyin display mode
- Authentication token (if logged in)
- Last analyzed text (draft)
- UI preferences

---

## Performance Features

### Optimizations

- **LRU caching** - Fast word lookups (10,000 entry cache)
- **Translation cache** - Reduce API calls and improve speed
- **Lazy loading** - HSK vocabulary loaded in background
- **Rate limiting** - Prevents API abuse (30/min analyze, 20/min translate)
- **Efficient segmentation** - jieba optimized for Chinese

### Speed

- **Instant local lookups** - HSK words from local database
- **Background processing** - Long operations don't block UI
- **Progressive loading** - Results appear as they're ready
- **Cached translations** - Instant for repeated phrases

---

## Tips & Best Practices

### For Best Results

1. **Paste clean text** - Remove unnecessary line breaks
2. **Use appropriate length** - 100-500 characters works best
3. **Save interesting texts** - Build your personal library
4. **Use vocabulary lists** - Organize words by topic or difficulty
5. **Track progress** - Mark how far you've read

### Learning Strategies

1. **Start with easier texts** - Begin with HSK 1-2 heavy texts
2. **Build vocabulary** - Add unknown words to your lists
3. **Practice pronunciation** - Use text-to-speech feature
4. **Review regularly** - Revisit saved texts and vocabulary
5. **Track your progress** - See improvement over time

### Mobile Usage

- **Long-press** instead of click for sentence translation
- **Pinch to zoom** if text is small
- **Use landscape** mode for longer texts
- **Save to home screen** for quick access (PWA coming soon)

---

## Keyboard Shortcuts

Coming soon:

- `Ctrl/Cmd + Enter` - Analyze text
- `Ctrl/Cmd + S` - Save text
- `Escape` - Close modals
- `Tab` - Navigate between inputs

---

## Planned Features

Features currently in development or planned:

- **Dark mode** - Reduce eye strain
- **Anki export** - Export vocabulary to Anki flashcards
- **CSV export** - Export lists to spreadsheets
- **Spaced repetition** - Built-in SRS system
- **Reading statistics** - Track your learning progress
- **Grammar hints** - Basic grammar explanations
- **Example sentences** - See words in context
- **Pronunciation practice** - Record and compare
- **Progress tracking** - Long-term learning analytics

---

For questions or feature requests, please [open an issue](https://github.com/mkampl/qingdu/issues) on GitHub.
