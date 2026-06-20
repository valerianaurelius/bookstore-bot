import asyncio
import logging
import os
import aiosqlite
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

DB_NAME = 'books.db'
IMAGES_DIR = 'images'
DEFAULT_IMAGE = 'no_cover.png'  # must exist in IMAGES_DIR

# ================== DATABASE ==================
async def init_db():
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute('''
            CREATE TABLE IF NOT EXISTS books (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                author TEXT NOT NULL,
                price INTEGER NOT NULL,
                category TEXT NOT NULL,
                image_file TEXT,
                file_path TEXT
            )
        ''')
        await db.execute('''
            CREATE TABLE IF NOT EXISTS cart_items (
                user_id INTEGER NOT NULL,
                book_id INTEGER NOT NULL,
                quantity INTEGER DEFAULT 1,
                PRIMARY KEY (user_id, book_id)
            )
        ''')
        # Seed data if empty
        cursor = await db.execute('SELECT COUNT(*) FROM books')
        if (await cursor.fetchone())[0] == 0:
            sample_books = [
                # All books use DEFAULT_IMAGE unless you have real images
                ('The Little Prince', 'Antoine de Saint-Exupéry', 95000, 'Fiction',
                 'little_prince.jpg', 'sample_books/little_prince.txt'),
                ('One Hundred Years of Solitude', 'Gabriel García Márquez', 145000, 'Fiction',
                 'hundred_years.jpg', 'sample_books/hundred_years.txt'),
                ('Sapiens', 'Yuval Noah Harari', 170000, 'Science',
                 'sapiens.jpg', 'sample_books/sapiens.txt'),
                ('A Brief History of Time', 'Stephen Hawking', 120000, 'Science',
                 'brief_history_time.jpg', 'sample_books/brief_history_time.txt'),
                ('Iran Between Two Revolutions', 'Ervand Abrahamian', 155000, 'History',
                 'iran_revolutions.jpg', 'sample_books/iran_revolutions.txt'),
                ('War and Peace', 'Leo Tolstoy', 195000, 'Fiction',
                 'war_peace.jpg', 'sample_books/war_peace.txt'),
                ('The Art of Clear Thinking', 'Rolf Dobelli', 105000, 'Psychology',
                 'clear_thinking.jpg', 'sample_books/clear_thinking.txt'),
                ('The Forty Rules of Love', 'Elif Shafak', 110000, 'Fiction',
                 'forty_rules.jpg', 'sample_books/forty_rules.txt'),
                ('The Game of Life', 'Florence Scovel Shinn', 85000, 'Psychology',
                 'game_of_life.jpg', 'sample_books/game_of_life.txt'),
                ('Content Inc.', 'Joe Pulizzi', 130000, 'Business',
                 'content_inc.jpg', 'sample_books/content_inc.txt'),
                ('Atomic Habits', 'James Clear', 95000, 'Psychology',
                 'atomic_habits.jpg', 'sample_books/atomic_habits.txt'),
                ('Limitless', 'Jim Kwik', 115000, 'Psychology',
                 'limitless.jpg', 'sample_books/limitless.txt'),
                ('The Wealth of Nations', 'Adam Smith', 185000, 'Economics',
                 'wealth_nations.jpg', 'sample_books/wealth_nations.txt'),
                ('The Art of War', 'Sun Tzu', 55000, 'History',
                 'art_of_war.jpg', 'sample_books/art_of_war.txt'),
            ]
            await db.executemany(
                'INSERT INTO books (title, author, price, category, image_file, file_path) VALUES (?,?,?,?,?,?)',
                sample_books
            )
            await db.commit()

# ================== UTILS ==================
async def get_categories():
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute('SELECT DISTINCT category FROM books ORDER BY category')
        return [row[0] for row in await cursor.fetchall()]

async def get_books_by_category(category: str):
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute('SELECT id, title, author, price FROM books WHERE category=? ORDER BY title', (category,))
        return await cursor.fetchall()

async def get_book(book_id: int):
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute('SELECT id, title, author, price, image_file, file_path, category FROM books WHERE id=?', (book_id,))
        return await cursor.fetchone()

async def add_to_cart(user_id: int, book_id: int):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute(
            'INSERT INTO cart_items (user_id, book_id) VALUES (?,?) ON CONFLICT(user_id,book_id) DO UPDATE SET quantity=quantity+1',
            (user_id, book_id)
        )
        await db.commit()

async def remove_from_cart(user_id: int, book_id: int):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute('DELETE FROM cart_items WHERE user_id=? AND book_id=?', (user_id, book_id))
        await db.commit()

async def get_cart(user_id: int):
    async with aiosqlite.connect(DB_NAME) as db:
        cursor = await db.execute('''
            SELECT b.id, b.title, b.price, c.quantity, b.file_path
            FROM cart_items c JOIN books b ON c.book_id = b.id
            WHERE c.user_id=?
        ''', (user_id,))
        return await cursor.fetchall()

async def clear_cart(user_id: int):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute('DELETE FROM cart_items WHERE user_id=?', (user_id,))
        await db.commit()

def get_image_path(image_file):
    """Return full path to image, or fallback to default."""
    path = os.path.join(IMAGES_DIR, image_file)
    if os.path.exists(path):
        return path
    # fallback
    default_path = os.path.join(IMAGES_DIR, DEFAULT_IMAGE)
    if os.path.exists(default_path):
        return default_path
    return None

# ================== UI RENDERING ==================
async def main_menu_reply(query, text="🏠 Main Menu:"):
    keyboard = [
        [InlineKeyboardButton("📚 Browse Books", callback_data='browse')],
        [InlineKeyboardButton("🛒 View Cart", callback_data='cart')],
        [InlineKeyboardButton("ℹ️ About Us", callback_data='about')],
        [InlineKeyboardButton("📞 Contact Us", callback_data='contact')]
    ]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

async def categories_menu(query):
    cats = await get_categories()
    keyboard = [[InlineKeyboardButton(cat, callback_data=f'cat_{cat}')] for cat in cats]
    keyboard.append([InlineKeyboardButton("🔙 Main Menu", callback_data='back_home')])
    await query.edit_message_text("📂 Select a category:", reply_markup=InlineKeyboardMarkup(keyboard))

async def books_in_category_menu(query, category):
    books = await get_books_by_category(category)
    if not books:
        await query.edit_message_text("No books found.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data='browse')]]))
        return
    text = f"*Books in {category}:*\nTap a book to view details."
    keyboard = []
    for book_id, title, author, price in books:
        keyboard.append([InlineKeyboardButton(f"📖 {title} - {price:,} IRR", callback_data=f'book_{book_id}')])
    keyboard.append([InlineKeyboardButton("🔙 Categories", callback_data='browse')])
    keyboard.append([InlineKeyboardButton("🏠 Main Menu", callback_data='back_home')])
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

async def show_book_photo(query, book_id):
    book = await get_book(book_id)
    if not book:
        await query.answer("Book not found.")
        return
    _, title, author, price, image_file, _, category = book
    caption = f"📖 *{title}*\n✍️ {author}\n💰 {price:,} IRR"
    keyboard = [
        [InlineKeyboardButton("🛒 Buy", callback_data=f'buy_{book_id}')],
        [InlineKeyboardButton("🔙 Back to Category", callback_data=f'back_cat_{category}')]
    ]
    image_path = get_image_path(image_file)
    logger.info(f"📸 Showing book: {title}, image_file={image_file}, resolved_path={image_path}")
    if image_path:
        try:
            with open(image_path, 'rb') as f:
                await query.message.chat.send_photo(
                    photo=f,
                    caption=caption,
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    parse_mode='Markdown'
                )
            await query.delete_message()
            logger.info("✅ Photo sent successfully.")
        except Exception as e:
            logger.error(f"❌ Failed to send photo: {e}")
            # fallback to text message
            await query.edit_message_text(
                caption,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='Markdown'
            )
    else:
        logger.warning("⚠️ No image path found, using text fallback.")
        await query.edit_message_text(
            caption,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
async def buy_book_and_show_options(query, user_id, book_id):
    await add_to_cart(user_id, book_id)
    book = await get_book(book_id)
    if not book:
        await query.answer("Error.")
        return
    caption = f"✅ *Added to cart!*\n📖 {book[1]}\n💰 {book[3]:,} IRR"
    keyboard = [
        [InlineKeyboardButton("🛒 View Cart", callback_data='cart')],
        [InlineKeyboardButton("📚 Continue Shopping", callback_data='browse')],
        [InlineKeyboardButton("🔙 Back to Book", callback_data=f'book_{book_id}')]
    ]
    await query.edit_message_caption(caption=caption, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    await query.answer("Added to cart ✅", show_alert=False)

async def show_cart(query, user_id):
    items = await get_cart(user_id)
    if not items:
        await query.edit_message_text("🛒 Your cart is empty.",
                                      reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Main Menu", callback_data='back_home')]]))
        return
    total = 0
    text = "🛒 *Your Shopping Cart:*\n\n"
    keyboard = []
    for book_id, title, price, qty, _ in items:
        item_total = price * qty
        total += item_total
        text += f"• {title} (Qty: {qty}) - {item_total:,} IRR\n"
        keyboard.append([InlineKeyboardButton(f"❌ Remove {title}", callback_data=f'remove_{book_id}')])
    text += f"\n💰 *Total: {total:,} IRR*"
    keyboard.append([InlineKeyboardButton("💳 Proceed to Checkout", callback_data='checkout')])
    keyboard.append([InlineKeyboardButton("🏠 Main Menu", callback_data='back_home')])
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

async def checkout_process(query, user_id):
    items = await get_cart(user_id)
    if not items:
        await query.edit_message_text("Your cart is empty.")
        return
    await query.edit_message_text("Processing payment... ⏳")
    await asyncio.sleep(1)
    for book_id, title, price, qty, file_path in items:
        if file_path and os.path.exists(file_path):
            with open(file_path, 'rb') as f:
                await query.message.chat.send_document(document=f, filename=f"{title.replace(' ', '_')}.txt",
                                                       caption=f"📥 {title}")
        else:
            await query.message.chat.send_message(f"⚠️ File for '{title}' not found.")
    await clear_cart(user_id)
    keyboard = [[InlineKeyboardButton("🏠 Main Menu", callback_data='back_home')]]
    await query.message.chat.send_message("✅ Payment successful! Your books have been delivered. Thank you! 🙏",
                                          reply_markup=InlineKeyboardMarkup(keyboard))

# ================== MAIN HANDLERS ==================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("📚 Browse Books", callback_data='browse')],
        [InlineKeyboardButton("🛒 View Cart", callback_data='cart')],
        [InlineKeyboardButton("ℹ️ About Us", callback_data='about')],
        [InlineKeyboardButton("📞 Contact Us", callback_data='contact')]
    ]
    await update.message.reply_text("Welcome to our Bookstore! 📖\nWhat would you like to do?",
                                    reply_markup=InlineKeyboardMarkup(keyboard))

async def router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    user_id = query.from_user.id

    if data == 'browse':
        await categories_menu(query)
    elif data.startswith('cat_'):
        category = data[4:]
        await books_in_category_menu(query, category)
    elif data.startswith('book_'):
        book_id = int(data[5:])
        await show_book_photo(query, book_id)
    elif data.startswith('buy_'):
        book_id = int(data[4:])
        await buy_book_and_show_options(query, user_id, book_id)
    elif data.startswith('remove_'):
        book_id = int(data[7:])
        await remove_from_cart(user_id, book_id)
        await show_cart(query, user_id)
    elif data == 'cart':
        await show_cart(query, user_id)
    elif data == 'checkout':
        await checkout_process(query, user_id)
    elif data.startswith('back_cat_'):
        category = data[9:]
        await books_in_category_menu(query, category)
    elif data == 'about':
        await query.edit_message_text("We are a small bookstore built with Python ❤️",
                                      reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Main Menu", callback_data='back_home')]]))
    elif data == 'contact':
        await query.edit_message_text("Email: bookstore@example.com",
                                      reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Main Menu", callback_data='back_home')]]))
    elif data == 'back_home':
        await main_menu_reply(query)

if __name__ == '__main__':
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(init_db())
    logger.info("Database ready.")

    TOKEN = os.environ.get("BOT_TOKEN")
    if not TOKEN:
        raise ValueError("BOT_TOKEN environment variable not set!")
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(router))

    logger.info("Bot is running...")
    app.run_polling()
