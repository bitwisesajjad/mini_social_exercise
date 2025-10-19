from flask import Flask, render_template, request, redirect, url_for, session, flash, g
from werkzeug.security import generate_password_hash, check_password_hash
from cryptography.fernet import Fernet
import collections
import json
import sqlite3
import hashlib
import re
from datetime import datetime

app = Flask(__name__)
app.secret_key = '123456789' 
DATABASE = 'database.sqlite'
# These are the stop words that I use in the exerceise 3.3 when building a recommendation system.
STOP_WORDS = {
    'a', 'an', 'and', 'are', 'as', 'at', 'be', 'by', 'for', 'from',
    'has', 'he', 'in', 'is', 'it', 'its', 'of', 'on', 'that', 'the',
    'to', 'was', 'will', 'with', 'i', 'me', 'my', 'you', 'your',
    'this', 'but', 'what', 'when', 'where', 'who', 'we', 'they',
    'she', 'her', 'him', 'them', 'their', 'or', 'if', 'so', 'there',
    'have', 'had', 'can', 'do', 'does', 'am', 'been', 'being', 'not',
    'just', 'like', 'get', 'got', 'very', 'much', 'more', 'about'
}
# Load censorship data
# WARNING! The censorship.dat file contains disturbing language when decrypted. 
# If you want to test whether moderation works, 
# you can trigger censorship using these words: 
# tier1badword, tier2badword, tier3badword
ENCRYPTED_FILE_PATH = 'censorship.dat'
fernet = Fernet('xpplx11wZUibz0E8tV8Z9mf-wwggzSrc21uQ17Qq2gg=')
with open(ENCRYPTED_FILE_PATH, 'rb') as encrypted_file:
    encrypted_data = encrypted_file.read()
decrypted_data = fernet.decrypt(encrypted_data)
MODERATION_CONFIG = json.loads(decrypted_data)
TIER1_WORDS = MODERATION_CONFIG['categories']['tier1_severe_violations']['words']
TIER2_PHRASES = MODERATION_CONFIG['categories']['tier2_spam_scams']['phrases']
TIER3_WORDS = MODERATION_CONFIG['categories']['tier3_mild_profanity']['words']

def get_db():
    """
    Connect to the application's configured database. The connection
    is unique for each request and will be reused if this is called
    again.
    """
    if 'db' not in g:
        g.db = sqlite3.connect(
            DATABASE,
            detect_types=sqlite3.PARSE_DECLTYPES
        )
        g.db.row_factory = sqlite3.Row

    return g.db


@app.teardown_appcontext
def close_connection(exception):
    """Closes the database again at the end of the request."""
    db = g.pop('db', None)

    if db is not None:
        db.close()


def query_db(query, args=(), one=False, commit=False):
    """
    Queries the database and returns a list of dictionaries, a single
    dictionary, or None. Also handles write operations.
    """
    db = get_db()
    
    # Using 'with' on a connection object implicitly handles transactions.
    # The 'with' statement will automatically commit if successful, 
    # or rollback if an exception occurs. This is safer.
    try:
        with db:
            cur = db.execute(query, args)
        
        # For SELECT statements, fetch the results after the transaction block
        if not commit:
            rv = cur.fetchall()
            return (rv[0] if rv else None) if one else rv
        
        # For write operations, we might want the cursor to get info like lastrowid
        return cur

    except sqlite3.Error as e:
        print(f"Database error: {e}")
        return None

@app.template_filter('datetimeformat')
def datetimeformat(value):
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, str):
        dt = datetime.strptime(value, '%Y-%m-%d %H:%M:%S')
    else:
        return "N/A"
    return dt.strftime('%b %d, %Y %H:%M')

REACTION_EMOJIS = {
    'like': '❤️', 'love': '😍', 'laugh': '😂',
    'wow': '😮', 'sad': '😢', 'angry': '😠',
}
REACTION_TYPES = list(REACTION_EMOJIS.keys())


@app.route('/')
def feed():
    #  1. Get Pagination and Filter Parameters 
    try:
        page = int(request.args.get('page', 1))
    except ValueError:
        page = 1
    sort = request.args.get('sort', 'new').lower()
    show = request.args.get('show', 'all').lower()
    
    # Define how many posts to show per page
    POSTS_PER_PAGE = 10
    offset = (page - 1) * POSTS_PER_PAGE

    current_user_id = session.get('user_id')
    params = []

    #  2. Build the Query 
    where_clause = ""
    if show == 'following' and current_user_id:
        where_clause = "WHERE p.user_id IN (SELECT followed_id FROM follows WHERE follower_id = ?)"
        params.append(current_user_id)

    # Add the pagination parameters to the query arguments
    pagination_params = (POSTS_PER_PAGE, offset)

    if sort == 'popular':
        query = f"""
            SELECT p.id, p.content, p.created_at, u.username, u.id as user_id,
                   IFNULL(r.total_reactions, 0) as total_reactions
            FROM posts p
            JOIN users u ON p.user_id = u.id
            LEFT JOIN (
                SELECT post_id, COUNT(*) as total_reactions FROM reactions GROUP BY post_id
            ) r ON p.id = r.post_id
            {where_clause}
            ORDER BY total_reactions DESC, p.created_at DESC
            LIMIT ? OFFSET ?
        """
        final_params = params + list(pagination_params)
        posts = query_db(query, final_params)
    elif sort == 'recommended':
        posts = recommend(current_user_id, show == 'following' and current_user_id)
    else:  # Default sort is 'new'
        query = f"""
            SELECT p.id, p.content, p.created_at, u.username, u.id as user_id
            FROM posts p
            JOIN users u ON p.user_id = u.id
            {where_clause}
            ORDER BY p.created_at DESC
            LIMIT ? OFFSET ?
        """
        final_params = params + list(pagination_params)
        posts = query_db(query, final_params)

    posts_data = []
    for post in posts:
        # Determine if the current user follows the poster
        followed_poster = False
        if current_user_id and post['user_id'] != current_user_id:
            follow_check = query_db(
                'SELECT 1 FROM follows WHERE follower_id = ? AND followed_id = ?',
                (current_user_id, post['user_id']),
                one=True
            )
            if follow_check:
                followed_poster = True

        # Determine if the current user reacted to this post and with what reaction
        user_reaction = None
        if current_user_id:
            reaction_check = query_db(
                'SELECT reaction_type FROM reactions WHERE user_id = ? AND post_id = ?',
                (current_user_id, post['id']),
                one=True
            )
            if reaction_check:
                user_reaction = reaction_check['reaction_type']

        reactions = query_db('SELECT reaction_type, COUNT(*) as count FROM reactions WHERE post_id = ? GROUP BY reaction_type', (post['id'],))
        comments_raw = query_db('SELECT c.id, c.content, c.created_at, u.username, u.id as user_id FROM comments c JOIN users u ON c.user_id = u.id WHERE c.post_id = ? ORDER BY c.created_at ASC', (post['id'],))
        post_dict = dict(post)
        post_dict['content'], _ = moderate_content(post_dict['content'])
        comments_moderated = []
        for comment in comments_raw:
            comment_dict = dict(comment)
            comment_dict['content'], _ = moderate_content(comment_dict['content'])
            comments_moderated.append(comment_dict)
        posts_data.append({
            'post': post_dict,
            'reactions': reactions,
            'user_reaction': user_reaction,
            'followed_poster': followed_poster,
            'comments': comments_moderated
        })

    #  4. Render Template with Pagination Info 
    return render_template('feed.html.j2', 
                           posts=posts_data, 
                           current_sort=sort,
                           current_show=show,
                           page=page, # Pass current page number
                           per_page=POSTS_PER_PAGE, # Pass items per page
                           reaction_emojis=REACTION_EMOJIS,
                           reaction_types=REACTION_TYPES)

@app.route('/posts/new', methods=['POST'])
def add_post():
    """Handles creating a new post from the feed."""
    user_id = session.get('user_id')

    # Block access if user is not logged in
    if not user_id:
        flash('You must be logged in to create a post.', 'danger')
        return redirect(url_for('login'))

    # Get content from the submitted form
    content = request.form.get('content')

    # Pass the user's content through the moderation function
    moderated_content = content

    # Basic validation to ensure post is not empty
    if moderated_content and moderated_content.strip():
        db = get_db()
        db.execute('INSERT INTO posts (user_id, content) VALUES (?, ?)',
                   (user_id, moderated_content))
        db.commit()
        flash('Your post was successfully created!', 'success')
    else:
        # This will catch empty posts or posts that were fully censored
        flash('Post cannot be empty or was fully censored.', 'warning')

    # Redirect back to the main feed to see the new post
    return redirect(url_for('feed'))
    
    
@app.route('/posts/<int:post_id>/delete', methods=['POST'])
def delete_post(post_id):
    """Handles deleting a post."""
    user_id = session.get('user_id')

    # Block access if user is not logged in
    if not user_id:
        flash('You must be logged in to delete a post.', 'danger')
        return redirect(url_for('login'))

    # Find the post in the database
    post = query_db('SELECT id, user_id FROM posts WHERE id = ?', (post_id,), one=True)

    # Check if the post exists and if the current user is the owner
    if not post:
        flash('Post not found.', 'danger')
        return redirect(url_for('feed'))

    if post['user_id'] != user_id:
        # Security check: prevent users from deleting others' posts
        flash('You do not have permission to delete this post.', 'danger')
        return redirect(url_for('feed'))

    # If all checks pass, proceed with deletion
    db = get_db()
    # To maintain database integrity, delete associated records first
    db.execute('DELETE FROM comments WHERE post_id = ?', (post_id,))
    db.execute('DELETE FROM reactions WHERE post_id = ?', (post_id,))
    # Finally, delete the post itself
    db.execute('DELETE FROM posts WHERE id = ?', (post_id,))
    db.commit()

    flash('Your post was successfully deleted.', 'success')
    # Redirect back to the page the user came from, or the feed as a fallback
    return redirect(request.referrer or url_for('feed'))

@app.route('/u/<username>')
def user_profile(username):
    """Displays a user's profile page with moderated bio, posts, and latest comments."""
    
    user_raw = query_db('SELECT * FROM users WHERE username = ?', (username,), one=True)
    if not user_raw:
        abort(404)

    user = dict(user_raw)
    moderated_bio, _ = moderate_content(user.get('profile', ''))
    user['profile'] = moderated_bio

    posts_raw = query_db('SELECT id, content, user_id, created_at FROM posts WHERE user_id = ? ORDER BY created_at DESC', (user['id'],))
    posts = []
    for post_raw in posts_raw:
        post = dict(post_raw)
        moderated_post_content, _ = moderate_content(post['content'])
        post['content'] = moderated_post_content
        posts.append(post)

    comments_raw = query_db('SELECT id, content, user_id, post_id, created_at FROM comments WHERE user_id = ? ORDER BY created_at DESC LIMIT 100', (user['id'],))
    comments = []
    for comment_raw in comments_raw:
        comment = dict(comment_raw)
        moderated_comment_content, _ = moderate_content(comment['content'])
        comment['content'] = moderated_comment_content
        comments.append(comment)

    followers_count = query_db('SELECT COUNT(*) as cnt FROM follows WHERE followed_id = ?', (user['id'],), one=True)['cnt']
    following_count = query_db('SELECT COUNT(*) as cnt FROM follows WHERE follower_id = ?', (user['id'],), one=True)['cnt']

    #  NEW: CHECK FOLLOW STATUS 
    is_currently_following = False # Default to False
    current_user_id = session.get('user_id')
    
    # We only need to check if a user is logged in
    if current_user_id:
        follow_relation = query_db(
            'SELECT 1 FROM follows WHERE follower_id = ? AND followed_id = ?',
            (current_user_id, user['id']),
            one=True
        )
        if follow_relation:
            is_currently_following = True
    # --

    return render_template('user_profile.html.j2', 
                           user=user, 
                           posts=posts, 
                           comments=comments,
                           followers_count=followers_count, 
                           following_count=following_count,
                           is_following=is_currently_following)
    

@app.route('/u/<username>/followers')
def user_followers(username):
    user = query_db('SELECT * FROM users WHERE username = ?', (username,), one=True)
    if not user:
        abort(404)
    followers = query_db('''
        SELECT u.username
        FROM follows f
        JOIN users u ON f.follower_id = u.id
        WHERE f.followed_id = ?
    ''', (user['id'],))
    return render_template('user_list.html.j2', user=user, users=followers, title="Followers of")

@app.route('/u/<username>/following')
def user_following(username):
    user = query_db('SELECT * FROM users WHERE username = ?', (username,), one=True)
    if not user:
        abort(404)
    following = query_db('''
        SELECT u.username
        FROM follows f
        JOIN users u ON f.followed_id = u.id
        WHERE f.follower_id = ?
    ''', (user['id'],))
    return render_template('user_list.html.j2', user=user, users=following, title="Users followed by")

@app.route('/posts/<int:post_id>')
def post_detail(post_id):
    """Displays a single post and its comments, with content moderation applied."""
    
    post_raw = query_db('''
        SELECT p.id, p.content, p.created_at, u.username, u.id as user_id
        FROM posts p
        JOIN users u ON p.user_id = u.id
        WHERE p.id = ?
    ''', (post_id,), one=True)

    if not post_raw:
        # The abort function will stop the request and show a 404 Not Found page.
        abort(404)

    #  Moderation for the Main Post 
    # Convert the raw database row to a mutable dictionary
    post = dict(post_raw)
    # Unpack the tuple from moderate_content, we only need the moderated content string here
    moderated_post_content, _ = moderate_content(post['content'])
    post['content'] = moderated_post_content

    #  Fetch Reactions (No moderation needed) 
    reactions = query_db('''
        SELECT reaction_type, COUNT(*) as count
        FROM reactions
        WHERE post_id = ?
        GROUP BY reaction_type
    ''', (post_id,))

    #  Fetch and Moderate Comments 
    comments_raw = query_db('SELECT c.id, c.content, c.created_at, u.username, u.id as user_id FROM comments c JOIN users u ON c.user_id = u.id WHERE c.post_id = ? ORDER BY c.created_at ASC', (post_id,))
    
    comments = [] # Create a new list for the moderated comments
    for comment_raw in comments_raw:
        comment = dict(comment_raw) # Convert to a dictionary
        # Moderate the content of each comment
        print(comment['content'])
        moderated_comment_content, _ = moderate_content(comment['content'])
        comment['content'] = moderated_comment_content
        comments.append(comment)

    # Pass the moderated data to the template
    return render_template('post_detail.html.j2',
                           post=post,
                           reactions=reactions,
                           comments=comments,
                           reaction_emojis=REACTION_EMOJIS,
                           reaction_types=REACTION_TYPES)

@app.route('/about')
def about():
    return render_template('about.html.j2')

@app.route('/privacy')
def privacy():
    return render_template('privacy.html.j2')


@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        location = request.form.get('location', '')
        birthdate = request.form.get('birthdate', '')
        profile = request.form.get('profile', '')

        hashed_password = generate_password_hash(password)

        db = get_db()
        cur = db.cursor()
        try:
            cur.execute(
                'INSERT INTO users (username, password, location, birthdate, profile) VALUES (?, ?, ?, ?, ?)',
                (username, hashed_password, location, birthdate, profile)
            )
            db.commit()

            # 1. Get the ID of the user we just created.
            new_user_id = cur.lastrowid

            # 2. Add user info to the session cookie.
            session.clear() # Clear any old session data
            session['user_id'] = new_user_id
            session['username'] = username

            # 3. Flash a welcome message and redirect to the feed.
            flash(f'Welcome, {username}! Your account has been created.', 'success')
            return redirect(url_for('feed')) # Redirect to the main feed/dashboard

        except sqlite3.IntegrityError:
            flash('Username already taken. Please choose another one.', 'danger')
        finally:
            cur.close()
            db.close()
            
    return render_template('signup.html.j2')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        db = get_db()
        user = db.execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone()
        db.close()

        # 1. Check if the user exists.
        # 2. If user exists, use check_password_hash to securely compare the password.
        #    This function handles the salt and prevents timing attacks.
        if user and check_password_hash(user['password'], password):
            # Password is correct!
            session['user_id'] = user['id']
            session['username'] = user['username']
            flash('Logged in successfully.', 'success')
            return redirect(url_for('feed'))
        else:
            # User does not exist or password was incorrect.
            flash('Invalid username or password.', 'danger')
            
    return render_template('login.html.j2')

@app.route('/logout')
def logout():
    session.clear()
    flash('Logged out.', 'info')
    return redirect(url_for('login'))

@app.route('/posts/<int:post_id>/comment', methods=['POST'])
def add_comment(post_id):
    """Handles adding a new comment to a specific post."""
    user_id = session.get('user_id')

    # Block access if user is not logged in
    if not user_id:
        flash('You must be logged in to comment.', 'danger')
        return redirect(url_for('login'))

    # Get content from the submitted form
    content = request.form.get('content')

    # Basic validation to ensure comment is not empty
    if content and content.strip():
        db = get_db()
        db.execute('INSERT INTO comments (post_id, user_id, content) VALUES (?, ?, ?)',
                   (post_id, user_id, content))
        db.commit()
        flash('Your comment was added.', 'success')
    else:
        flash('Comment cannot be empty.', 'warning')

    # Redirect back to the page the user came from (likely the post detail page)
    return redirect(request.referrer or url_for('post_detail', post_id=post_id))

@app.route('/comments/<int:comment_id>/delete', methods=['POST'])
def delete_comment(comment_id):
    """Handles deleting a comment."""
    user_id = session.get('user_id')

    # Block access if user is not logged in
    if not user_id:
        flash('You must be logged in to delete a comment.', 'danger')
        return redirect(url_for('login'))

    # Find the comment and the original post's author ID
    comment = query_db('''
        SELECT c.id, c.user_id, p.user_id as post_author_id
        FROM comments c
        JOIN posts p ON c.post_id = p.id
        WHERE c.id = ?
    ''', (comment_id,), one=True)

    # Check if the comment exists
    if not comment:
        flash('Comment not found.', 'danger')
        return redirect(request.referrer or url_for('feed'))

    # Security Check: Allow deletion if the user is the comment's author OR the post's author
    if user_id != comment['user_id'] and user_id != comment['post_author_id']:
        flash('You do not have permission to delete this comment.', 'danger')
        return redirect(request.referrer or url_for('feed'))

    # If all checks pass, proceed with deletion
    db = get_db()
    db.execute('DELETE FROM comments WHERE id = ?', (comment_id,))
    db.commit()

    flash('Comment successfully deleted.', 'success')
    # Redirect back to the page the user came from
    return redirect(request.referrer or url_for('feed'))

@app.route('/react', methods=['POST'])
def add_reaction():
    """Handles adding a new reaction or updating an existing one."""
    user_id = session.get('user_id')

    if not user_id:
        flash("You must be logged in to react.", "danger")
        return redirect(url_for('login'))

    post_id = request.form.get('post_id')
    new_reaction_type = request.form.get('reaction')

    if not post_id or not new_reaction_type:
        flash("Invalid reaction request.", "warning")
        return redirect(request.referrer or url_for('feed'))

    db = get_db()

    # Step 1: Check if a reaction from this user already exists on this post.
    existing_reaction = query_db('SELECT id FROM reactions WHERE post_id = ? AND user_id = ?',
                                 (post_id, user_id), one=True)

    if existing_reaction:
        # Step 2: If it exists, UPDATE the reaction_type.
        db.execute('UPDATE reactions SET reaction_type = ? WHERE id = ?',
                   (new_reaction_type, existing_reaction['id']))
    else:
        # Step 3: If it does not exist, INSERT a new reaction.
        db.execute('INSERT INTO reactions (post_id, user_id, reaction_type) VALUES (?, ?, ?)',
                   (post_id, user_id, new_reaction_type))

    db.commit()

    return redirect(request.referrer or url_for('feed'))

@app.route('/unreact', methods=['POST'])
def unreact():
    """Handles removing a user's reaction from a post."""
    user_id = session.get('user_id')

    if not user_id:
        flash("You must be logged in to unreact.", "danger")
        return redirect(url_for('login'))

    post_id = request.form.get('post_id')

    if not post_id:
        flash("Invalid unreact request.", "warning")
        return redirect(request.referrer or url_for('feed'))

    db = get_db()

    # Remove the reaction if it exists
    existing_reaction = query_db(
        'SELECT id FROM reactions WHERE post_id = ? AND user_id = ?',
        (post_id, user_id),
        one=True
    )

    if existing_reaction:
        db.execute('DELETE FROM reactions WHERE id = ?', (existing_reaction['id'],))
        db.commit()
        flash("Reaction removed.", "success")
    else:
        flash("No reaction to remove.", "info")

    return redirect(request.referrer or url_for('feed'))


@app.route('/u/<int:user_id>/follow', methods=['POST'])
def follow_user(user_id):
    """Handles the logic for the current user to follow another user."""
    follower_id = session.get('user_id')

    # Security: Ensure user is logged in
    if not follower_id:
        flash("You must be logged in to follow users.", "danger")
        return redirect(url_for('login'))

    # Security: Prevent users from following themselves
    if follower_id == user_id:
        flash("You cannot follow yourself.", "warning")
        return redirect(request.referrer or url_for('feed'))

    # Check if the user to be followed actually exists
    user_to_follow = query_db('SELECT id FROM users WHERE id = ?', (user_id,), one=True)
    if not user_to_follow:
        flash("The user you are trying to follow does not exist.", "danger")
        return redirect(request.referrer or url_for('feed'))
        
    db = get_db()
    try:
        # Insert the follow relationship. The PRIMARY KEY constraint will prevent duplicates if you've set one.
        db.execute('INSERT INTO follows (follower_id, followed_id) VALUES (?, ?)',
                   (follower_id, user_id))
        db.commit()
        username_to_follow = query_db('SELECT username FROM users WHERE id = ?', (user_id,), one=True)['username']
        flash(f"You are now following {username_to_follow}.", "success")
    except sqlite3.IntegrityError:
        flash("You are already following this user.", "info")

    return redirect(request.referrer or url_for('feed'))


@app.route('/u/<int:user_id>/unfollow', methods=['POST'])
def unfollow_user(user_id):
    """Handles the logic for the current user to unfollow another user."""
    follower_id = session.get('user_id')

    # Security: Ensure user is logged in
    if not follower_id:
        flash("You must be logged in to unfollow users.", "danger")
        return redirect(url_for('login'))

    db = get_db()
    cur = db.execute('DELETE FROM follows WHERE follower_id = ? AND followed_id = ?',
               (follower_id, user_id))
    db.commit()

    if cur.rowcount > 0:
        # cur.rowcount tells us if a row was actually deleted
        username_unfollowed = query_db('SELECT username FROM users WHERE id = ?', (user_id,), one=True)['username']
        flash(f"You have unfollowed {username_unfollowed}.", "success")
    else:
        # This case handles if someone tries to unfollow a user they weren't following
        flash("You were not following this user.", "info")

    # Redirect back to the page the user came from
    return redirect(request.referrer or url_for('feed'))

@app.route('/admin')
def admin_dashboard():
    """Displays the admin dashboard with users, posts, and comments, sorted by risk."""

    if session.get('username') != 'admin':
        flash("You do not have permission to access this page.", "danger")
        return redirect(url_for('feed'))

    RISK_LEVELS = { "HIGH": 5, "MEDIUM": 3, "LOW": 1 }
    PAGE_SIZE = 50

    def get_risk_profile(score):
        if score >= RISK_LEVELS["HIGH"]:
            return "HIGH", 3
        elif score >= RISK_LEVELS["MEDIUM"]:
            return "MEDIUM", 2
        elif score >= RISK_LEVELS["LOW"]:
            return "LOW", 1
        return "NONE", 0

    # Get pagination and current tab parameters
    try:
        users_page = int(request.args.get('users_page', 1))
        posts_page = int(request.args.get('posts_page', 1))
        comments_page = int(request.args.get('comments_page', 1))
    except ValueError:
        users_page = 1
        posts_page = 1
        comments_page = 1
    
    current_tab = request.args.get('tab', 'users') # Default to 'users' tab

    users_offset = (users_page - 1) * PAGE_SIZE
    
    # First, get all users to calculate risk, then apply pagination in Python
    # It's more complex to do this efficiently in SQL if risk calc is Python-side
    all_users_raw = query_db('SELECT id, username, profile, created_at FROM users')
    all_users = []
    for user in all_users_raw:
        user_dict = dict(user)
        user_risk_score = user_risk_analysis(user_dict['id'])
        risk_label, risk_sort_key = get_risk_profile(user_risk_score)
        user_dict['risk_label'] = risk_label
        user_dict['risk_sort_key'] = risk_sort_key
        user_dict['risk_score'] = min(5.0, round(user_risk_score, 2))
        all_users.append(user_dict)

    all_users.sort(key=lambda x: x['risk_score'], reverse=True)
    total_users = len(all_users)
    users = all_users[users_offset : users_offset + PAGE_SIZE]
    total_users_pages = (total_users + PAGE_SIZE - 1) // PAGE_SIZE

    # --- Posts Tab Data ---
    posts_offset = (posts_page - 1) * PAGE_SIZE
    total_posts_count = query_db('SELECT COUNT(*) as count FROM posts', one=True)['count']
    total_posts_pages = (total_posts_count + PAGE_SIZE - 1) // PAGE_SIZE

    posts_raw = query_db(f'''
        SELECT p.id, p.content, p.created_at, u.username, u.created_at as user_created_at
        FROM posts p JOIN users u ON p.user_id = u.id
        ORDER BY p.id DESC -- Order by ID for consistent pagination before risk sort
        LIMIT ? OFFSET ?
    ''', (PAGE_SIZE, posts_offset))
    posts = []
    for post in posts_raw:
        post_dict = dict(post)
        _, base_score = moderate_content(post_dict['content'])
        final_score = base_score 
        author_created_dt = post_dict['user_created_at']
        author_age_days = (datetime.utcnow() - author_created_dt).days
        if author_age_days < 7:
            final_score *= 1.5
        risk_label, risk_sort_key = get_risk_profile(final_score)
        post_dict['risk_label'] = risk_label
        post_dict['risk_sort_key'] = risk_sort_key
        post_dict['risk_score'] = round(final_score, 2)
        posts.append(post_dict)

    posts.sort(key=lambda x: x['risk_score'], reverse=True) # Sort after fetching and scoring

    # --- Comments Tab Data ---
    comments_offset = (comments_page - 1) * PAGE_SIZE
    total_comments_count = query_db('SELECT COUNT(*) as count FROM comments', one=True)['count']
    total_comments_pages = (total_comments_count + PAGE_SIZE - 1) // PAGE_SIZE

    comments_raw = query_db(f'''
        SELECT c.id, c.content, c.created_at, u.username, u.created_at as user_created_at
        FROM comments c JOIN users u ON c.user_id = u.id
        ORDER BY c.id DESC -- Order by ID for consistent pagination before risk sort
        LIMIT ? OFFSET ?
    ''', (PAGE_SIZE, comments_offset))
    comments = []
    for comment in comments_raw:
        comment_dict = dict(comment)
        _, score = moderate_content(comment_dict['content'])
        author_created_dt = comment_dict['user_created_at']
        author_age_days = (datetime.utcnow() - author_created_dt).days
        if author_age_days < 7:
            score *= 1.5
        risk_label, risk_sort_key = get_risk_profile(score)
        comment_dict['risk_label'] = risk_label
        comment_dict['risk_sort_key'] = risk_sort_key
        comment_dict['risk_score'] = round(score, 2)
        comments.append(comment_dict)

    comments.sort(key=lambda x: x['risk_score'], reverse=True) # Sort after fetching and scoring


    return render_template('admin.html.j2', 
                           users=users, 
                           posts=posts, 
                           comments=comments,
                           
                           # Pagination for Users
                           users_page=users_page,
                           total_users_pages=total_users_pages,
                           users_has_next=(users_page < total_users_pages),
                           users_has_prev=(users_page > 1),

                           # Pagination for Posts
                           posts_page=posts_page,
                           total_posts_pages=total_posts_pages,
                           posts_has_next=(posts_page < total_posts_pages),
                           posts_has_prev=(posts_page > 1),

                           # Pagination for Comments
                           comments_page=comments_page,
                           total_comments_pages=total_comments_pages,
                           comments_has_next=(comments_page < total_comments_pages),
                           comments_has_prev=(comments_page > 1),

                           current_tab=current_tab,
                           PAGE_SIZE=PAGE_SIZE)



@app.route('/admin/delete/user/<int:user_id>', methods=['POST'])
def admin_delete_user(user_id):
    if session.get('username') != 'admin':
        flash("You do not have permission to perform this action.", "danger")
        return redirect(url_for('feed'))
        
    if user_id == session.get('user_id'):
        flash('You cannot delete your own account from the admin panel.', 'danger')
        return redirect(url_for('admin_dashboard'))
    
    db = get_db()
    db.execute('DELETE FROM users WHERE id = ?', (user_id,))
    db.commit()
    flash(f'User {user_id} and all their content has been deleted.', 'success')
    return redirect(url_for('admin_dashboard'))


@app.route('/admin/delete/post/<int:post_id>', methods=['POST'])
def admin_delete_post(post_id):
    if session.get('username') != 'admin':
        flash("You do not have permission to perform this action.", "danger")
        return redirect(url_for('feed'))

    db = get_db()
    db.execute('DELETE FROM comments WHERE post_id = ?', (post_id,))
    db.execute('DELETE FROM reactions WHERE post_id = ?', (post_id,))
    db.execute('DELETE FROM posts WHERE id = ?', (post_id,))
    db.commit()
    flash(f'Post {post_id} has been deleted.', 'success')
    return redirect(url_for('admin_dashboard'))


@app.route('/admin/delete/comment/<int:comment_id>', methods=['POST'])
def admin_delete_comment(comment_id):
    if session.get('username') != 'admin':
        flash("You do not have permission to perform this action.", "danger")
        return redirect(url_for('feed'))

    db = get_db()
    db.execute('DELETE FROM comments WHERE id = ?', (comment_id,))
    db.commit()
    flash(f'Comment {comment_id} has been deleted.', 'success')
    return redirect(url_for('admin_dashboard'))

@app.route('/rules')
def rules():
    return render_template('rules.html.j2')

@app.template_global()
def loop_color(user_id):
    # Generate a pastel color based on user_id hash
    h = hashlib.md5(str(user_id).encode()).hexdigest()
    r = int(h[0:2], 16)
    g = int(h[2:4], 16)
    b = int(h[4:6], 16)
    return f'rgb({r % 128 + 80}, {g % 128 + 80}, {b % 128 + 80})'



# ----- Functions to be implemented are below

# Task 3.1
def recommend(user_id, filter_following):
    """
    Args:
        user_id: The ID of the current user.
        filter_following: Boolean, True if we only want to see recommendations from followed users.

    Returns:
        A list of 5 recommended posts, in reverse-chronological order.

    To test whether your recommendation algorithm works, let's pretend we like the DIY topic. Here are some users that often post DIY comment and a few example posts. Make sure your account did not engage with anything else. You should test your algorithm with these and see if your recommendation algorithm picks up on your interest in DIY and starts showing related content.
    
    Users: @starboy99, @DancingDolphin, @blogger_bob
    Posts: 1810, 1875, 1880, 2113
    
    Materials: 
    - https://www.nvidia.com/en-us/glossary/recommendation-system/
    - http://www.configworks.com/mz/handout_recsys_sac2010.pdf
    - https://www.researchgate.net/publication/227268858_Recommender_Systems_Handbook
    """
    import sqlite3
    from collections import Counter
    import re
    
    conn = sqlite3.connect(DATABASE)
    # I use row_factory to access columns by name instead of index
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # In this section we should check and if the filter_following is set to True, we should only 
    # recommend posts for the users that the current user follows. However, if the filter is set to
    # False, I recommend posts from all the users.
    following_user_ids = []  
    if filter_following:
        # Get list of users that this user follows
        cursor.execute("SELECT followee_id FROM follows WHERE follower_id = ? ", (user_id,))
        following_user_ids = [row['followee_id'] for row in cursor.fetchall()]
        
        # If user doesn't follow anyone, I recommend posts from all users
        if not following_user_ids:
            filter_following = False
    
    #First, I should find all posts this user has liked/reacted to because these posts show 
    # what content the user is interested in. It is simple, I get the unique posts a user has 
    #reacted to. I say unique because a user may have multiple reactions to a single post.
    cursor.execute("SELECT DISTINCT p.id, p.content FROM posts p JOIN reactions r ON p.id = r.post_id WHERE r.user_id = ?", (user_id,))
    reacted_posts = cursor.fetchall()
    
    # In the following section, I loop through each of the post that the user has reacted to
    # and convert the content of those posts to lowercase and remove the stop words such as 
    # "the" or "but" or "an" and also remove the short words that have 1 or 2 character because
    # they are less likely to have any meaningful significance.
    # finally, after this processing, we get a list of more meaningful words like the following:
    #       Input: "I love programming in Python"
    #       After processing: ["love", "programming", "python"]

    all_words = []
    for post in reacted_posts:
        content = post['content'] 
        # If there are posts with no content, I  skip them!   
        if not content:
            continue
        
        # This extracts the words and removes punctuation and numbers
        words = re.findall(r'\b[a-z]+\b', content.lower())
        
        # Now I remove stop words and short words. Stop words are defined in STOP_WORDS
        # set at the top of this file
        meaningful_words = [
            word for word in words 
            if word not in STOP_WORDS and len(word) >= 2
        ]
        
        # we now add these keywords to our collection
        all_words.extend(meaningful_words)
    
    # Here I want to find the user's main interests based on the keyword frequency in the content
    # of the posts they reacted to. If the user has no reactions, we should find something to show,
    # so decided to show top 5 most popular posts. of course, i make sure the user's own posts are not
    # shown to them even if they are among the top 5 posts. here is an example: 
    #       Extracted keywords:["python", "python", "python", "coding", "data", "data"]
    #       Frequency: python(3 times), data(2times), coding(1 times)
    #       Top keywords: ["python", "data", "coding"]
    #       Interpretation: User is interested in Python programming and data  
    if not all_words:
        if filter_following and following_user_ids:
            # Only recommend from users the current user follows
            placeholders = ','.join('?' * len(following_user_ids))
            cursor.execute(f"SELECT p.*, COUNT(r.id) as reaction_count FROM posts p LEFT JOIN reactions r ON p.id = r.post_id WHERE p.user_id != ? AND p.user_id IN ({placeholders}) GROUP BY p.id ORDER BY reaction_count DESC LIMIT 5", [user_id] + following_user_ids)
        else:
            # Recommend popular posts from all users
            cursor.execute("SELECT p.*, COUNT(r.id) as reaction_count FROM posts p LEFT JOIN reactions r ON p.id = r.post_id WHERE p.user_id != ? GROUP BY p.id ORDER BY reaction_count DESC LIMIT 5", (user_id,))
        results = cursor.fetchall()
        conn.close()
        # Return full post objects
        return results
    
    # Counter creates a dictionary: {"python": 3, "data": 2, "coding": 1}
    word_counter = Counter(all_words)
    
    # Here I get top 15 most common words to create a diverse recommendation
    top_keywords = [word for word, count in word_counter.most_common(15)]
    
    # Now, i find the posts that i can recommend. They should not be made by the user and 
    # they should be new to user. Of course, if the filter_following is set to True, we should only 
    # recommend posts from those this user is following and this will become another restricting factor
    # in recommendation process.
    if filter_following and following_user_ids:
        # Only get posts from users we follow
        placeholders = ','.join('?' * len(following_user_ids))
        cursor.execute(f"SELECT p.id, p.content FROM posts p WHERE p.id NOT IN (SELECT post_id FROM reactions WHERE user_id = ?) AND p.user_id != ? AND p.user_id IN ({placeholders})", [user_id, user_id] + following_user_ids)
    else:
        # Get posts from all users
        cursor.execute("SELECT p.id, p.content FROM posts p WHERE p.id NOT IN (SELECT post_id FROM reactions WHERE user_id = ?) AND p.user_id != ?", (user_id, user_id))
    
    candidate_posts = cursor.fetchall()
    
    # in this section, i create a scoring algorithm to find the best posts to recommend to the user. 
    # i first extract the words from the candidate posts and check how many of the interest
    # keywords are in those posts. For each matching, i give +1 score and the higher the accumulative 
    # score is, the more interesting that post will probably be to the user. 
    post_scores = []
    for post in candidate_posts:
        content = post['content']
        # I skip posts with no content
        if not content:
            continue
        
        # This line extracts words from this candidate post
        post_words = re.findall(r'\b[a-z]+\b', content.lower())
        
        # calculating the relevance and giving a score:
        score = 0
        for keyword in top_keywords:
            if keyword in post_words:
                score += 1
        
        # Only include posts with at least one keyword match
        # Posts with score 0 are not relevant to user's interests
        if score > 0:
            post_scores.append((post['id'], score))
    
    # Here I sort scores which are the second element of the tuple using a lambda function and 
    # sorting using the score which is the index 1. the reverse makes the highest score appear first.
    post_scores.sort(key=lambda x: x[1], reverse=True)
    
    # Now, we can get top 5 recommendations as post IDs
    recommended_post_ids = [post_id for post_id, score in post_scores[:5]]
    
    # If we have fewer than 5 recommendations, fill with popular posts to ensure we always
    # return 5 recommendations when possible
    if len(recommended_post_ids) < 5:
        # Collect IDs of posts to exclude (already recommended or already reacted to)
        excluded_ids = set(recommended_post_ids)
        excluded_ids.update([post['id'] for post in reacted_posts])
        
        placeholders = ','.join('?' * len(excluded_ids)) if excluded_ids else '0'
        
        if filter_following and following_user_ids:
            # Fill with popular posts from users we follow
            following_placeholders = ','.join('?' * len(following_user_ids))
            cursor.execute(f"SELECT p.id, COUNT(r.id) as reaction_count FROM posts p LEFT JOIN reactions r ON p.id = r.post_id WHERE p.id NOT IN ({placeholders}) AND p.user_id != ? AND p.user_id IN ({following_placeholders}) GROUP BY p.id ORDER BY reaction_count DESC LIMIT ? ", list(excluded_ids) + [user_id] + following_user_ids + [5 - len(recommended_post_ids)])
        else:
            # Fill with popular posts from all users
            cursor.execute(f"SELECT p.id, COUNT(r.id) as reaction_count FROM posts p LEFT JOIN reactions r ON p.id = r.post_id  WHERE p.id NOT IN ({placeholders}) AND p.user_id != ? GROUP BY p.id ORDER BY reaction_count DESC LIMIT ? ", list(excluded_ids) + [user_id, 5 - len(recommended_post_ids)])
        additional_posts = cursor.fetchall()
        recommended_post_ids.extend([row['id'] for row in additional_posts])
    
    # Now fetch full post objects for the recommended post IDs
    if recommended_post_ids:
        placeholders = ','.join('?' * len(recommended_post_ids))
        cursor.execute(f"""
            SELECT * FROM posts 
            WHERE id IN ({placeholders})
        """, recommended_post_ids)
        final_posts = cursor.fetchall()
    else:
        final_posts = []
    
    conn.close()
    # Return full post objects (up to 5)
    return final_posts[:5]

# Task 3.2 =======================================================================
def user_risk_analysis(user_id):
    """
    Args:
        user_id: The ID of the user on which we perform risk analysis.

    Returns:
        A float number score showing the risk associated with this user. There are no strict rules or bounds to this score, other than that a score of less than 1.0 means no risk, 1.0 to 3.0 is low risk, 3.0 to 5.0 is medium risk and above 5.0 is high risk. (An upper bound of 5.0 is applied to this score elsewhere in the codebase) 
        
        You will be able to check the scores by logging in with the administrator account:
            username: admin
            password: admin
        Then, navigate to the /admin endpoint. (http://localhost:8080/admin)
    """
    import sqlite3
    from datetime import datetime
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # First I need to get the user profile and the date that the suer joined the platform so 
    # i have the bio and the age of the account. 
    cursor.execute("SELECT profile, created_at FROM users WHERE id = ?", (user_id,))
    user = cursor.fetchone()
    
    if not user:
        conn.close()
        return 0.0
    
    # Now, I get the bio for each user and then pass it through the moderation 
    # module that I created in exdercise 3.1. This will help us calculate profile score.
    profile_text = user['profile'] if user['profile'] else ''
    _, profile_score = moderate_content(profile_text)
    

    # We do the same but this time we analyze the posts the user has created and finnaly calculate 
    # the average score of all posts. Here i used the method "user_id =?" followed by (user_id,)
    # to prevent sql injection, as instructed by the TA in exercise sessions. The same will be true
    # about when I calculate the average score for the comments of this user. 
    cursor.execute("SELECT content FROM posts WHERE user_id = ?", (user_id,))
    posts = cursor.fetchall()
    post_scores = []
    for post in posts:
        post_content = post['content'] if post['content'] else ''
        _, post_score = moderate_content(post_content)
        post_scores.append(post_score)
    # now we should divide the scores of all posts by the number of the posts. 
    average_post_score = sum(post_scores) / len(post_scores) if len(post_scores) > 0 else 0.0
    

    # In this step, I calculate the average score for the comments this user has created. 
    # just like the process we had for the average post scores.
    cursor.execute("SELECT content FROM comments WHERE user_id = ?", (user_id,))
    comments = cursor.fetchall()
    comment_scores = []
    for comment in comments:
        comment_content = comment['content'] if comment['content'] else ''
        _, comment_score = moderate_content(comment_content)
        comment_scores.append(comment_score)
    average_comment_score = sum(comment_scores) / len(comment_scores) if len(comment_scores) > 0 else 0.0
    

    # Now that we have all the scores for profile (a.k.a Bio), comments and posts, 
    # I calculate the weighted average according to the importance of each of these elements
    # as I described before I provided the codes. We should divide the weighted sum by 5 to get the 
    #weighted average. 
    content_risk_score = ((profile_score * 1) + (average_post_score * 3) + (average_comment_score * 1)) / 5
    
    
    # Now, we should apply the effect of age of the user's accound. Based on this age,
    #  we impose different risk multipliers and the younger the account is, the higher this 
    # age multiplier will be. By doing so, we are in fact more suspicious of younger 
    # accounds and the more mature accounts are considered more legitimate and less suspicious.
    # This is simply because spammers usually create an account and post many things 
    # and when their violations are caught, they just create new accounds and this age 
    # multiplier can help us catch them much faster because they will be flagged more often 
    # than the mature ones. 
    created_at_str = user['created_at']
    try:
        created_at = datetime.strptime(created_at_str, '%Y-%m-%d %H:%M:%S')
    except (ValueError, TypeError):
        created_at = datetime.now()
    
    current_time = datetime.now()
    account_age_days = (current_time - created_at).days
    
    # Here we DEFINE the age multiplier. The accounts that are older than three month old (90 days)
    # are not affected at all.
    if account_age_days < 30:
        age_multiplier = 1.5
    elif account_age_days < 90:
        age_multiplier = 1.2
    else:
        age_multiplier = 1.0
    
    #and now we APPLY it:
    user_risk_score = content_risk_score * age_multiplier
    
    # ==========================================================================
    # CUSTOM RISK MEASURE: NEGATIVE ENGAGEMENT ANALYSIS
    # ==========================================================================
    # My custom measure is "Negative engagement risk measure" and it analyzes how other users
    # respond to the posts a user creates by giving their reactions. My idea was that sometimes
    # content moderation cannot catch the more hidden profanity and spamming and it may fail 
    # when it deals with more subtle profanity or rudeness. However, users almost always catch 
    # these and react to them. By analyzing those reactions, we can identify even the most
    # subtle and hidden toxic materials on the platform.
    #
    # I assigned a numerical weight to each reaction type and using these weights I quantifies the user's received reactions from other users.  here are the summary of the weights:
    #  - "Angry" is -1 because it means the person who left an angry reaction is showing strong negative emotion. 
    #  - "Sad" is 0 because it is emotionally ambiguous and it can simply show that the user is empathizing with the post. 
    #  - all the happy reactions such as Like, Love, haha, Wow will receive a +1 because they show that the users are appreciating the post and it is less likely to be a bad or violating one. 
    #For each user, I collect all the reactions on their posts and calculate their weighted average. Then, I divide this sum by the total number of reactions to get a normalized ratio that will range between -1 and +1. This "sentiment ratio" shows the average sentiment of the whole community of users interacting with that user's post on our platform. 
    #Finally, I apply risk penalty based on the user's sentiment ratio. a ratio under -0.3 means almost 65 to 70 percent of the users are not happy with the posts and this can be a good trigger.  -0.3 to -0.5 is considered moderate and receives +0.3 to their risk score.  is the sentiment ratio is between -0.5 and -0.7 i add 0.5 to their risk score and if the sentiment ratio is less than -0.7 i add 1 to their risk score. 
    
    cursor.execute("SELECT r.reaction_type FROM reactions r JOIN posts p ON r.post_id = p.id WHERE p.user_id = ?", (user_id,))
    reactions = cursor.fetchall()
    sentiment_score = 0
    total_reactions = 0
    
    for reaction in reactions:
        reaction_type = reaction['reaction_type']
        total_reactions += 1
        
        if reaction_type == 'angry':
            sentiment_score += -1  
        elif reaction_type == 'sad':
            sentiment_score += 0 
        elif reaction_type in ['like', 'haha', 'love', 'wow']:
            sentiment_score += 1 
        else:
            sentiment_score += 0 #this is for unknown ractions. We can add more reactions if 
            # we see that they are used on the platform. For the sake of simplicity and 
            # merely showing how this works, i have only considered the reactions that we have 
            # on the platform now. 
    
    # For negative sentiment penalty, I first check if teh user has any reactions or not. 
    # I will apply this only if user has received reactions.
    if total_reactions > 0:
        sentiment_ratio = sentiment_score / total_reactions
        
        # ANow we apply penalty for negative sentiment based on the description I gave above.
        if sentiment_ratio < -0.3:
            if sentiment_ratio < -0.7:
                user_risk_score += 1.0
            elif sentiment_ratio < -0.5:
                user_risk_score += 0.5
            else:
                user_risk_score += 0.3
    # =============END OF CUSTOM RISK MEASURE ==================================

    # Cap at 5.0
    if user_risk_score > 5.0:
        user_risk_score = 5.0
    
    conn.close()
    return user_risk_score

# Now, I should create the classification of the user based on the score I calculated
# in the previous section. 
# I call the users with a risk score of less than 1, as LOW RISK users. Users with risk scores of 
# 1 to 3, are MEDIUM RISK, and those with a risk score of between 3 to 4.5 are HIGH RISK.
# Finally, those whose score is more than 4.5 are catagorized as DANGEROUS! 
def classify_risk(score):
    if score < 1.0:
        return "Low risk"
    elif score < 3.0:
        return "Medium risk"
    elif score < 4.5:
        return "High risk"
    else:
        return "Dangerous!"
    score = 0

    return score;

    
# Task 3.3 =======================================================================

def moderate_content(content):
    if not content or content.strip()== '':
        return content, 0
    
    # If content is None, empty string "", or just whitespace " ", return it as it is and
    # give a score of 0. Of course I should admit that the chance of somebody posting an empty
    #post is None! but to just consider all the possible scenarios, here I considered it. 
    score = 0
    moderated = content 

    # TIER 1 ---------------------------------------------------------------
    content_lower=content.lower()
    for bad_word in TIER1_WORDS:
        
        # Here we need to make sure that the Tier1 words are used alone and separately
        # in the content because othersise we may wrongly flag a word that is 
        # ok and not rude. 
        # The pattern I used is:    r'\bhell\b'                       
        # This will make sure the words are considered separately. 
        # "go to hell" : it is not Ok because we have the word "hell" and must be moderated. 
        # However, "hello there" should be left untouched even though there is a "hell" in hello!

        pattern = r'\b' + re.escape(bad_word.lower()) + r'\b'
        if re.search(pattern, content_lower):
            return "[content is removed due to severe violation]", 5
    
    # TIER 2 ---------------------------------------------------------------
    # For Tier 2 because we are checking the phrases, and not the words, 
    # and therefore it is irrelevant because the chance of having a complete phrase in a 
    # word is zero!
    for spam_phrase in TIER2_PHRASES:
        if spam_phrase.lower() in content_lower:
            return "[content removed due to spam/scam policy]", 5
    
    
    # TIER 3 ---------------------------------------------------------------
    words = moderated.split()
    cleaned_words = []
    for word in words:
        word_clean = re.sub(r'[^\w]', '', word.lower())
        word_found = False
        for profane_word in TIER3_WORDS:
            
            # Here again we need to make sure the words are separately and not a part of 
            # another word. This is just like the Tier 1 so I do not exxplain repeatedly. 
            pattern = r'\b' + re.escape(profane_word.lower()) + r'\b'
            if re.search(pattern, word_clean):
                
                # Here I find the bad words that are in Tier 3, I do not remove
                # the whole content but put asterisks instead of the word. So, that is why
                # in the line bellow i calculated the length of the bad word that we have identified
                # and replaced the word buy the same number of asterisks.
                masked = '*' * len(word)
                cleaned_words.append(masked)
                score += 2
                word_found = True
                break
        
        # If no profanity was found in this word, we do not change the word and leave it as
        #it is and go to the next word. 
        if not word_found:
            cleaned_words.append(word)
    
    # Finally, using the following join operation, I put all the words that were
    # were either moderated or left untouched next to eachother to make the moderated sentence. 
    moderated = ' '.join(cleaned_words)
    

    # URL DETECTION ---------------------------------------------------------------
    # In order to detect the different types of urls i defined the following pattern:
    # First I had to consider both http and https so i used this:
    # https?://[^\s]+
    # then  
    # using  www\.[^\s]+   I create a pattern for www. followed by one or more non space
    # characters.
    # In the end, [a-zA-Z0-9-]+\.(com|org|net|edu|gov|io)[^\s]*   is the pattern for the
    # domain name and the final domain. I put some most common domains. But I know that 
    # more domains should be included here. 
    url_pattern = r'https?://[^\s]+|www\.[^\s]+|[a-zA-Z0-9-]+\.(com|org|net|edu|gov|io)[^\s]*'
    urls_found = re.findall(url_pattern, moderated)
    url_count = len(urls_found)
    moderated = re.sub(url_pattern, '[link removed]', moderated, flags=re.IGNORECASE)
    score += url_count * 2

    # --------------------------------------------------------------------------
    # One more moderation measure: Mention spam  -------------------------------
    # --------------------------------------------------------------------------
    # This is my custom moderation measure. It detects too much use of mentions 
    # in a single post and moderates it.
    #
    # Why is this a problem?
    # - Spammers mention many users to appear in their notifications which is a violation.
    # - Spammers bypass URL filters by using mentions and attracting people to their profile
    # - This annoys mentioned users who get unwanted notifications
    # - It shows some sort of marketing behavior that is intrusive. 
    #
    # Threshold: 5 mentions or more
    # Normal group conversations might mention up to 3 to 4 people
    # So: "Hey @Sajjad and @Atif, check this out" (2 mentions = OK)
    # 
    # More than 4 mentions is too much and it is suspicious
    # - So: "@user1 @user2 @user3 @user4 @user5 @user6 BUY NOW" (6 mentions = not OK = SPAM!)
    #
    # Scoring:
    # - I add 2 points to be consistent with other moderation rules
    # - I DON'T remove the mentions (users can see who was mentioned)
    # - The increased score flags the post for admin to review in order to make sure
    # the user is spamming or it was just an honest poor taste in mentioning!
    # --------------------------------------------------------------------------
    
    # regex pattern to match @mentions such as @sajjad, @user123, @sajjad_ghaemi, @teammarketing
    mention_pattern = r'@\w+'
    
    # Here we should find all @mentions in the content and return
    #  a list like: ['@sajjad', '@aku', '@daniel']
    mentions = re.findall(mention_pattern, moderated)
    if len(mentions) >= 5:
        score += 2
    
    # Before returning, we need to ensure the score doesn't exceed the maximum score of 5
    # because he risk scoring system uses 0-5 scale (defined in rules) and other parts
    # of the application expect scores less than or equal to 5.
    # I first tried to stop counting when a person reaches 5, but then realized that it 
    # is much nicer to count everything so when in the future the maximum changes, we can 
    # easily change the following two lines and we will be good to go!
        if score > 5:
            score = 5

    return moderated, score



if __name__ == '__main__':
    app.run(debug=True, port=8080)

