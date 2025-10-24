
## Exercise 4.1:Topic modeling with LDA ##

import sqlite3
import re
from collections import Counter
from gensim import corpora
from gensim.models import LdaModel
import nltk

# I decided to manually copy some of the most common stopwords here because for some strange reasons
  # I couldn't get it from nltk.download and puytting them here seemed more practical for this 
 # exercise.  
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


#Connecting to database 
# >>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>

print("Extracting data from database")
# .......................................

# First I connect to the database, and since these steps are already explained in the previous exercises, i won't go
# into too much details. 
# 
# The first step is to connect to the database and create a cursor to get id and content of all the posts that 
# have a content and are not empty.
DATABASE = 'database.sqlite'
conn = sqlite3.connect(DATABASE)
cursor = conn.cursor()
cursor.execute("SELECT id, content from posts where content IS NOT NULL")
posts = cursor.fetchall()

#Now we do the same for the comments and get all the comments as well. 
cursor.execute("select id, content from comments where content IS NOT NULL")
comments = cursor.fetchall()
conn.close()

# for the sake of information, I show how m,any posts and how many comments I found. 
print(f"✓ Found and copied the content of {len(posts)} posts")
print(f"✓ found {len(comments)} comments and got their content too")
print(f"✓ Now i have to analyze {len(posts) + len(comments)} contents.")
print()

#Preparing texts
# >>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>
print ("Preparing text data ...")
# Here, i have to combine all text content into one list and each item in this list is the content of either a post or a comment
documents = []
## first I start with poosts and add them to the document
for post_id, content in posts:
    if content:
        documents.append(content)
# now I do it for comments
for comment_id, content in comments:
    if content:
        documents.append(content)

#Text preprocessing (We should do some cleaning and create tokens)
# >>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>
print ("Text preprocessing ...")
def preprocess_text(text):
    
    #Before performing LDA analysis, I have to do some cleaning and preparation of the text data in order to get
    # more accurate results in the topic modeling stage. First, the preprocessing was performed by turning all text to lowercase
    # in order to make sure that words such as "Python" and "python" are considered and processed as the same words. 
    #Then, URLs are removed because they do not add meaningful information in the process of topic modeling. 
    # Then i remove special characters and numbers because just like the urls, they don't add any value to the topic modelling.
    # in fact, we only keep alphabetic content in contents of posts and comments. After that, text must be tokenized, 
    # which means the splitting of text into individual words for easier analysis.

     #After tokenization, common stop words like "the" and "is" should be removed because they add minimum value to the process in temrs of 
     # meaning of sentences. Very short words, usually less than three characters, are also ignored in order to reduce the noise in the data set. This means that 
     # a sentence like "I am running to that store in Oulu" would be reduced to the list ["running", "that" ,"store", "Oulu"], which are the words
     # that are most useful in topic modeling. 
    
    # converting to lowercase
    text = text.lower()
    #removing URLs
    text = re.sub(r'http\S+|www\S+', '', text)
     #deleting special characters and numbers, keep only letters and spaces
    text = re.sub(r'[^a-z\s]', '', text)
     # split into words 
    tokens = text.split()
    
    #removing stop words and short words
    processed_tokens = []
    for token in tokens:
        if token in STOP_WORDS:
            continue
        if len(token) < 3:
            continue
        # in the above two lines i ignore the words rthat are too short and are only one or two letters. 
        processed_tokens.append(token)
    return processed_tokens

#now we should process all documents.
print("Now I will processing all the documkents...")
print("It will be over soon. Take a sip at your coffee and lay back!")
# to make sure things are going on, and we are not hitting a wall, 
# I print the progress every 1000 documents.
processed_documents = []
for i, doc in enumerate(documents):
    if (i + 1) % 1000 == 0:
        print(f"  Processed {i + 1}/{len(documents)} documents...")
    tokens = preprocess_text(doc)
# the documents that have less than 2 meaningful words /tokens are ignored. 
    #if len(tokens) >= 2:   # when this is set to 2, the percentages change and I'll mention it in my report
    # but it's an interesting observation because it adds around 170 words to the list f words and they change the proportions. 
    if len(tokens) >= 3:
        processed_documents.append(tokens)
print(f"✓ Preprocessing complete!")
print(f"✓ We have now {len(processed_documents)} to create a dictionary.")

# dictionary and corpus
# >>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>
print("creating dictionary and corpus for LDA ...")

#$# creating a dictionary
dictionary = corpora.Dictionary(processed_documents)

## we have to remove the words that arte either too common or too rare becuse they are some kind of noise. 
# none of them can help us distinguish between topics. 
print("Filtering dictionary...")
print(f"  Before filtering there were {len(dictionary)} unique words")
dictionary.filter_extremes(no_below=5, no_above=0.5)
print(f"  After filtering the words that were too common or too rare, we have {len(dictionary)} unique words")

corpus = [dictionary.doc2bow(doc) for doc in processed_documents]
print(f"✓ Now we have a dictionary with {len(dictionary)} unique words")
print(f"✓ We have a corpus with {len(corpus)} documents")


# STEP 5: Training LDA model
# >>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>
print("STEP 5: Training LDA model to find 10 topics")
print("  Number of topics: 10")
print("  Passes: 15")
print("This will take a few minutes... Finish that coffee...")

lda_model = LdaModel(
    corpus=corpus,
    id2word=dictionary,
    num_topics=10,
    random_state=42,
    passes=15,
    iterations=400,
    per_word_topics=True
)

print("✓ LDA training complete!")

# Displaying and analyzing the topics
# >>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>
print("Analyzing discovered topics ...")
# here i give the topics and some most important words
topics = lda_model.print_topics(num_words=10)

print("🔍 Discovered topics:")
topic_interpretations = []

for topic_id, topic_words in topics:
    print(f"Topic {topic_id + 1}: ")
    word_list = []
    for item in topic_words.split(' + '):
        word = item.split('*')[1].strip('"')
        word_list.append(word)
    
    print(f"Top words: {', '.join(word_list)}")
    
    # storing the raw topic string
    topic_interpretations.append({
        'topic_id': topic_id + 1,
        'words': word_list,
        'raw': topic_words
    })

# STEP 7: Topic distribution analysis
# >>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>
print("Analyzing topic distribution in documents")

# for each topic, i count how many documents that specific topic appears
topic_document_counts = Counter()
for doc_bow in corpus:
# this tells me what percentagre of the document belongs to each topic
    doc_topics = lda_model.get_document_topics(doc_bow)

    #finding the dominant topic (topic with the highest probability compared to others)
    if doc_topics:
        dominant_topic = max(doc_topics, key=lambda x: x[1])
        topic_document_counts[dominant_topic[0]] += 1

print("The popularity of the topic:")

# sort topics by popularity
sorted_topics = sorted(topic_document_counts.items(), key=lambda x: x[1], reverse=True)

for rank, (topic_id, count) in enumerate(sorted_topics, 1):
    percentage = (count / len(corpus)) * 100
    print(f"{rank}. Topic {topic_id + 1}: {count} documents ({percentage:.1f}%)")
    print(f"Top words: {', '.join(topic_interpretations[topic_id]['words'][:5])}")

# Saving results
# >>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>
print("saving results ...")

# save the model (so i can load it later without having to train everything again)
lda_model.save('lda_model_10_topics.model')
print("Model saved as 'lda_model_10_topics.model'")
# saving the dictionary
dictionary.save('lda_dictionary.dict')
print("Dictionary saved as 'lda_dictionary.dict'")

# save human-readable results to a text file
with open('topic_analysis_results.txt', 'w', encoding='utf-8') as f:
    f.write("dicovered topics:\n")
    f.write(">" * 70 + "\n\n")
    
    for topic_id, topic_words in topics:
        f.write(f"TOPIC {topic_id + 1}:\n")
        f.write(f"{topic_words}\n\n")
    
    f.write("\nPopularity of topics:\n")
    f.write(">" * 70 + "\n\n")
    
    for rank, (topic_id, count) in enumerate(sorted_topics, 1):
        percentage = (count / len(corpus)) * 100
        f.write(f"{rank}. Topic {topic_id + 1}: {count} documents ({percentage:.1f}%)\n")