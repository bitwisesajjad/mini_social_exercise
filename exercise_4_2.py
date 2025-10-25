#Exercise 4.2: sentiment analysis with VADER

import sqlite3
import pickle
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
from collections import Counter, defaultdict
from gensim import corpora
from gensim.models import LdaModel

print("Starting sentiment analysis with VADER...\n")

# STEP 1: Load LDA Model and Data from Exercise 4.1
# >>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>

# # I have to load LDA model from exercise 4.1. This connects our sentiment analysis to the topics we discovered in 4.1
try:
    lda_model = LdaModel.load('lda_model_10_topics.model')
    dictionary = corpora.Dictionary.load('lda_dictionary.dict')
    print("LDA model and dictionary loaded successfully")
except:
    print("ERROR: Could not load LDA model from Exercise 4.1")
    print("Make sure you ran exercise_4_1.py first and the files exist:")
    print("  - lda_model_10_topics.model")
    print("  - lda_dictionary.dict")
    exit(1)

print()

# STEP 2: Initialize VADER Sentiment Analyzer
# >>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>

# Create the VADER analyzer object
# This will be used to analyze sentiment of each post and comment
analyzer = SentimentIntensityAnalyzer()

# STEP 3: Extract Posts and Comments from Database
# >>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>


DATABASE = 'database.sqlite'
conn = sqlite3.connect(DATABASE)
cursor = conn.cursor()

# Get all posts with their IDs and content
# We keep the IDs so we can track which post has which sentiment
cursor.execute("SELECT id, content FROM posts WHERE content IS NOT NULL AND content != ''")
posts = cursor.fetchall()

# Get all comments with their IDs and content
cursor.execute("SELECT id, content FROM comments WHERE content IS NOT NULL AND content != ''")
comments = cursor.fetchall()

conn.close()

print(f"Extracted {len(posts)} posts")
print(f"Extracted {len(comments)} comments")
print(f"Total documents to analyze: {len(posts) + len(comments)}")
print()


# STEP 4: Analyze Sentiment of All Posts
# >>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>

# I'll store the sentiment scores for each post
post_sentiments = {}

# Counters for overall statistics
post_sentiment_counts = Counter()  # counts how many positive, negative, neutral posts
post_compound_scores = []  # list of all compound scores for average calculation

print("Analyzing posts...")
for post_id, content in posts:
    # getting sentiment scores from VADER
    # polarity_scores returns a dictionary with pos, neg, neu, and compound
    scores = analyzer.polarity_scores(content)
    
    # Extracting the compound score (this is our main metric)
    compound = scores['compound']
    
    # I will classify the sentiment based on compound score. The standard threshold is :
    # Standard thresholds: >= 0.05 is positive, <= -0.05 is negative
    if compound >= 0.05:
        sentiment = 'positive'
    elif compound <= -0.05:
        sentiment = 'negative'
    else:
        sentiment = 'neutral'
    
    # I store the results to use them later on when i am trying to calclulate average compound score /the overal tone of the platform. 
    post_sentiments[post_id] = {
        'content': content,
        'compound': compound,
        'sentiment': sentiment,
        'pos': scores['pos'],
        'neg': scores['neg'],
        'neu': scores['neu']
    }
    
    # The counter has to be updated....
    post_sentiment_counts[sentiment] += 1
    post_compound_scores.append(compound)

# Now we can calculate average compound score for posts.
average_post_compound = sum(post_compound_scores) / len(post_compound_scores)

print(f"Posts analyzed: {len(post_sentiments)}")
print(f"  Positive: {post_sentiment_counts['positive']} ({post_sentiment_counts['positive']/len(posts)*100:.1f}%)")
print(f"  Negative: {post_sentiment_counts['negative']} ({post_sentiment_counts['negative']/len(posts)*100:.1f}%)")
print(f"  Neutral: {post_sentiment_counts['neutral']} ({post_sentiment_counts['neutral']/len(posts)*100:.1f}%)")
print(f"  Average compound score: {average_post_compound:.3f}")
print()

# STEP 5: Analyze Sentiment of All Comments
# >>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>

# Here I will do what i did for posts, but for comments and save the compound score for the comments as well. 
comment_sentiments = {}
comment_sentiment_counts = Counter()
comment_compound_scores = []

print("Analyzing comments...")
for comment_id, content in comments:
    scores = analyzer.polarity_scores(content)
    compound = scores['compound']
    
    if compound >= 0.05:
        sentiment = 'positive'
    elif compound <= -0.05:
        sentiment = 'negative'
    else:
        sentiment = 'neutral'
    
    comment_sentiments[comment_id] = {
        'content': content,
        'compound': compound,
        'sentiment': sentiment,
        'pos': scores['pos'],
        'neg': scores['neg'],
        'neu': scores['neu']
    }
    
    comment_sentiment_counts[sentiment] += 1
    comment_compound_scores.append(compound)

# This is the average compound score for comments:
average_comment_compound = sum(comment_compound_scores) / len(comment_compound_scores)

print(f"Comments analyzed: {len(comment_sentiments)}")
print(f"  Positive: {comment_sentiment_counts['positive']} ({comment_sentiment_counts['positive']/len(comments)*100:.1f}%)")
print(f"  Negative: {comment_sentiment_counts['negative']} ({comment_sentiment_counts['negative']/len(comments)*100:.1f}%)")
print(f"  Neutral: {comment_sentiment_counts['neutral']} ({comment_sentiment_counts['neutral']/len(comments)*100:.1f}%)")
print(f"  Average compound score: {average_comment_compound:.3f}")
print()

# STEP 6: Calculate overall platform sentiment
# >>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>

# In order to calculate the overal sentiment of the social media platform, I need to combine posts and comments for overall statistics
total_documents = len(posts) + len(comments)
total_positive = post_sentiment_counts['positive'] + comment_sentiment_counts['positive']
total_negative = post_sentiment_counts['negative'] + comment_sentiment_counts['negative']
total_neutral = post_sentiment_counts['neutral'] + comment_sentiment_counts['neutral']

# Overall average compound score of the platform:
all_compound_scores = post_compound_scores + comment_compound_scores
overall_average_compound = sum(all_compound_scores) / len(all_compound_scores)

print(f"Total documents analyzed: {total_documents}")
print(f"  Positive: {total_positive} ({total_positive/total_documents*100:.1f}%)")
print(f"  Negative: {total_negative} ({total_negative/total_documents*100:.1f}%)")
print(f"  Neutral: {total_neutral} ({total_neutral/total_documents*100:.1f}%)")
print(f"  Overall average compound: {overall_average_compound:.3f}")
print()

# Usainf the above informationm, we can now determine overall platform tone
if overall_average_compound >= 0.05:
    platform_tone = "POSITIVE"
elif overall_average_compound <= -0.05:
    platform_tone = "NEGATIVE"
else:
    platform_tone = "NEUTRAL"

print(f"OVERALL PLATFORM TONE: {platform_tone}")
print()

# STEP 7: Preprocess Text for Topic Assignment (same as Exercise 4.1)
# >>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>

# We need to preprocess text the same way we did in Exercise 4.1
# so we can use the LDA model to assign topics

import re

STOP_WORDS = {
    'i', 'me', 'my', 'myself', 'we', 'our', 'ours', 'ourselves', 'you', "you're", "you've",
    "you'll", "you'd", 'your', 'yours', 'yourself', 'yourselves', 'he', 'him', 'his',
    'himself', 'she', "she's", 'her', 'hers', 'herself', 'it', "it's", 'its', 'itself',
    'they', 'them', 'their', 'theirs', 'themselves', 'what', 'which', 'who', 'whom',
    'this', 'that', "that'll", 'these', 'those', 'am', 'is', 'are', 'was', 'were', 'be',
    'been', 'being', 'have', 'has', 'had', 'having', 'do', 'does', 'did', 'doing', 'a',
    'an', 'the', 'and', 'but', 'if', 'or', 'because', 'as', 'until', 'while', 'of', 'at',
    'by', 'for', 'with', 'about', 'against', 'between', 'into', 'through', 'during',
    'before', 'after', 'above', 'below', 'to', 'from', 'up', 'down', 'in', 'out', 'on',
    'off', 'over', 'under', 'again', 'further', 'then', 'once', 'here', 'there', 'when',
    'where', 'why', 'how', 'all', 'both', 'each', 'few', 'more', 'most', 'other', 'some',
    'such', 'no', 'nor', 'not', 'only', 'own', 'same', 'so', 'than', 'too', 'very', 's',
    't', 'can', 'will', 'just', 'don', "don't", 'should', "should've", 'now', 'd', 'll',
    'm', 'o', 're', 've', 'y', 'ain', 'aren', "aren't", 'couldn', "couldn't", 'didn',
    "didn't", 'doesn', "doesn't", 'hadn', "hadn't", 'hasn', "hasn't", 'haven', "haven't",
    'isn', "isn't", 'ma', 'mightn', "mightn't", 'mustn', "mustn't", 'needn', "needn't",
    'shan', "shan't", 'shouldn', "shouldn't", 'wasn', "wasn't", 'weren', "weren't", 'won',
    "won't", 'wouldn', "wouldn't", 'get', 'got', 'like', 'also', 'would', 'could', 'going',
    'know', 'think', 'one', 'much', 'even', 'many', 'way', 'see', 'really', 'something',
    'make', 'made', 'want', 'well', 'still', 'back', 'im', 'ive', 'dont', 'cant', 'wont'
}

def preprocess_text(text):
    # same preprocessing as Exercise 4.1
    text = text.lower()
    text = re.sub(r'http\S+|www\S+', '', text)
    text = re.sub(r'[^a-z\s]', '', text)
    tokens = text.split()
    processed = []
    for token in tokens:
        if token not in STOP_WORDS and len(token) >= 3:
            processed.append(token)
    return processed

print("Text preprocessing function ready")
print()

# STEP 8: Assign Topics to Posts and Comments
# >>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>

# For each post and comment, we'll first (preprocess the text) and then (convert to bag-of-words using the dictionary). The next step will
#be to (use LDA model to get topic distribution). Finally, i will (assign the dominant topic).


#Assigning topics to posts
for post_id, content in posts:
    tokens = preprocess_text(content)
    # Skip if there are too few tokens to be analyzed.
    if len(tokens) < 2:
        post_sentiments[post_id]['topic'] = None
        continue
    bow = dictionary.doc2bow(tokens)
    # Get topic distribution from LDA model
    doc_topics = lda_model.get_document_topics(bow)
    
    # Now i will find the dominant topic that is technically the topic with highest probability
    if doc_topics:
        dominant_topic = max(doc_topics, key=lambda x: x[1])
        topic_id = dominant_topic[0]  # topic ID (0-9)
        topic_prob = dominant_topic[1]  # probability
        post_sentiments[post_id]['topic'] = topic_id
        post_sentiments[post_id]['topic_prob'] = topic_prob
    else:
        post_sentiments[post_id]['topic'] = None

# We do the same for the comments: 
# Assigning topics to comments...
for comment_id, content in comments:
    tokens = preprocess_text(content)
    if len(tokens) < 2:
        comment_sentiments[comment_id]['topic'] = None
        continue
    bow = dictionary.doc2bow(tokens)
    doc_topics = lda_model.get_document_topics(bow)
    
    if doc_topics:
        dominant_topic = max(doc_topics, key=lambda x: x[1])
        topic_id = dominant_topic[0]
        topic_prob = dominant_topic[1]
        comment_sentiments[comment_id]['topic'] = topic_id
        comment_sentiments[comment_id]['topic_prob'] = topic_prob
    else:
        comment_sentiments[comment_id]['topic'] = None

# STEP 9: Calculate Sentiment by Topic
# >>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>

# We'll create a structure to hold sentiment data for each topic
topic_sentiments = defaultdict(lambda: {
    'positive': 0,
    'negative': 0,
    'neutral': 0,
    'compounds': []
})

# collecting sentiment data for each topic from posts:
for post_id, data in post_sentiments.items():
    topic = data.get('topic')
    if topic is not None:
        sentiment = data['sentiment']
        compound = data['compound']
        topic_sentiments[topic][sentiment] += 1
        topic_sentiments[topic]['compounds'].append(compound)

# collecting sentiment data for each topic from comments:
for comment_id, data in comment_sentiments.items():
    topic = data.get('topic')
    if topic is not None:
        sentiment = data['sentiment']
        compound = data['compound']
        topic_sentiments[topic][sentiment] += 1
        topic_sentiments[topic]['compounds'].append(compound)

# Now, we need to calculate the average sentiment for each topic that we have. 
# Using what we did before, I get topic words for display (from Exercise 4.1)
topics = lda_model.print_topics(num_words=5)

for topic_id in range(10):
    # getting top words for this topic
    topic_words = topics[topic_id][1]
    word_list = []
    for item in topic_words.split(' + '):
        word = item.split('*')[1].strip('"')
        word_list.append(word)
    
    # getting sentiment counts for this topic
    pos = topic_sentiments[topic_id]['positive']
    neg = topic_sentiments[topic_id]['negative']
    neu = topic_sentiments[topic_id]['neutral']
    total = pos + neg + neu
    if total == 0:
        continue
    
    #calculating average compound score for this topic:
    compounds = topic_sentiments[topic_id]['compounds']
    avg_compound = sum(compounds) / len(compounds) if compounds else 0
    
    # As before, I can determine topic sentiment using the compound score
    if avg_compound >= 0.05:
        topic_sentiment = "POSITIVE"
    elif avg_compound <= -0.05:
        topic_sentiment = "NEGATIVE"
    else:
        topic_sentiment = "NEUTRAL"
    
    print(f"Topic {topic_id + 1}: {', '.join(word_list[:5])}")
    print(f"  Total documents: {total}")
    print(f"  Positive: {pos} ({pos/total*100:.1f}%)")
    print(f"  Negative: {neg} ({neg/total*100:.1f}%)")
    print(f"  Neutral: {neu} ({neu/total*100:.1f}%)")
    print(f"  Average compound: {avg_compound:.3f}")
    print(f"  Overall sentiment: {topic_sentiment}")
    print()

# STEP 10: Save Results
# >>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>

# Now I can save the results in a text file
with open('sentiment_analysis_results.txt', 'w', encoding='utf-8') as f:
    f.write("The result of sentiment analysis\n")
    f.write("=" * 70 + "\n\n")
    
    f.write("Overall platform sentiment\n")
    f.write("-" * 70 + "\n")
    f.write(f"Total documents: {total_documents}\n")
    f.write(f"Positive: {total_positive} ({total_positive/total_documents*100:.1f}%)\n")
    f.write(f"Negative: {total_negative} ({total_negative/total_documents*100:.1f}%)\n")
    f.write(f"Neutral: {total_neutral} ({total_neutral/total_documents*100:.1f}%)\n")
    f.write(f"Average compound: {overall_average_compound:.3f}\n")
    f.write(f"Overall tone: {platform_tone}\n\n")
    
    f.write("post sentiment\n")
    f.write("-" * 70 + "\n")
    f.write(f"Total posts: {len(posts)}\n")
    f.write(f"Positive: {post_sentiment_counts['positive']} ({post_sentiment_counts['positive']/len(posts)*100:.1f}%)\n")
    f.write(f"Negative: {post_sentiment_counts['negative']} ({post_sentiment_counts['negative']/len(posts)*100:.1f}%)\n")
    f.write(f"Neutral: {post_sentiment_counts['neutral']} ({post_sentiment_counts['neutral']/len(posts)*100:.1f}%)\n")
    f.write(f"Average compound: {average_post_compound:.3f}\n\n")
    
    f.write("comment sentiment\n")
    f.write("-" * 70 + "\n")
    f.write(f"Total comments: {len(comments)}\n")
    f.write(f"Positive: {comment_sentiment_counts['positive']} ({comment_sentiment_counts['positive']/len(comments)*100:.1f}%)\n")
    f.write(f"Negative: {comment_sentiment_counts['negative']} ({comment_sentiment_counts['negative']/len(comments)*100:.1f}%)\n")
    f.write(f"Neutral: {comment_sentiment_counts['neutral']} ({comment_sentiment_counts['neutral']/len(comments)*100:.1f}%)\n")
    f.write(f"Average compound: {average_comment_compound:.3f}\n\n")
    
    f.write("Sentiments of the Topiccs\n")
    f.write("=" * 70 + "\n\n")
    
    for topic_id in range(10):
        topic_words = topics[topic_id][1]
        word_list = []
        for item in topic_words.split(' + '):
            word = item.split('*')[1].strip('"')
            word_list.append(word)
        
        pos = topic_sentiments[topic_id]['positive']
        neg = topic_sentiments[topic_id]['negative']
        neu = topic_sentiments[topic_id]['neutral']
        total = pos + neg + neu
        
        if total == 0:
            continue
        
        compounds = topic_sentiments[topic_id]['compounds']
        avg_compound = sum(compounds) / len(compounds) if compounds else 0
        
        if avg_compound >= 0.05:
            topic_sentiment = "POSITIVE"
        elif avg_compound <= -0.05:
            topic_sentiment = "NEGATIVE"
        else:
            topic_sentiment = "NEUTRAL"
        
        f.write(f"Topic {topic_id + 1}: {', '.join(word_list[:5])}\n")
        f.write(f"  Total: {total}\n")
        f.write(f"  Positive: {pos} ({pos/total*100:.1f}%)\n")
        f.write(f"  Negative: {neg} ({neg/total*100:.1f}%)\n")
        f.write(f"  Neutral: {neu} ({neu/total*100:.1f}%)\n")
        f.write(f"  Avg compound: {avg_compound:.3f}\n")
        f.write(f"  Sentiment: {topic_sentiment}\n\n")

print("Results saved to sentiment_analysis_results.txt")
print(">" * 30)
print(f"  Platform tone: {platform_tone}")
print(f"  Overall average compound: {overall_average_compound:.3f}")
