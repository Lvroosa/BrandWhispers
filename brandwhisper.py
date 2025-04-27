





# --- IMPORTS ---
import praw
import pandas as pd
import streamlit as st
import altair as alt
from datetime import datetime
from google.genai import types
import asyncio
import nest_asyncio
import re
import time
import base64
import google.generativeai as genai


nest_asyncio.apply()


# GEMINI API SETUP
GEMINI_API_KEY = st.secrets["all_my_api_keys"]["GEMINI_API_KEY"]
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel(model_name="gemini-1.5-pro-latest")








# REDDIT API SETUP
reddit = praw.Reddit(
    client_id= st.secrets["all_my_api_keys"]["client_id"],
    client_secret= st.secrets["all_my_api_keys"]["client_secret"],
    user_agent= st.secrets["all_my_api_keys"]["user_agent"],
)












#gif background setup




gif_url = "https://media2.giphy.com/media/v1.Y2lkPTc5MGI3NjExb29wZ2V1bjl1azdkcXl6aTU0Zjlyb2wwbGpoNXBwcDMzbTNkdXF5NiZlcD12MV9pbnRlcm5hbF9naWZfYnlfaWQmY3Q9Zw/Hg5Bsk2WvDTUvhWs7E/giphy.gif"




st.markdown(
    f"""
    <style>
    .stApp {{
        background: url("{gif_url}") no-repeat center center fixed;
        background-size: cover;
        position: relative;
    }}
    .stApp::before {{
        content: "";
        position: fixed;
        top: 0;
        left: 0;
        height: 100%;
        width: 100%;
        background-color: rgba(255, 255, 255, 0.4);
        z-index: 0;
    }}
    .stApp > * {{
        position: relative;
        z-index: 1;
    }}
    </style>
    """,
    unsafe_allow_html=True
)








# --- STREAMLIT UI ---
st.title('Welcome to BrandWhispers!')
st.write("Not from surveys—straight from gossip forums.")








# --- USER INPUT ---
search_all = st.checkbox("Search across all conversations, not just one subreddit", value=False)
if not search_all:
    subreddit_name = st.text_input('Enter the brand subreddit (e.g., nike):', 'nike')
else:
    subreddit_name = "all"  # Automatically use 'all' for full-site search
keyword = st.text_input('Now enter a product or topic to snoop on:', 'shoes')
sort = st.selectbox('Snoop public opinion by:', ['relevance', 'hot', 'new'])
strict_filter = st.checkbox("Only include opinions that contain your chosen product.", value=True)
post_limit = st.slider("How many opinions do you want to analyze?",
    min_value=1,
    max_value=100,
    value=100,
    step=1
)




# --- FUNCTIONS ---
@st.cache_data
def get_top_opinions(subreddit_name, post_limit, keyword):
    subreddit = reddit.subreddit(subreddit_name)
    top_posts = []
    for submission in subreddit.search(keyword, sort=sort, time_filter='all', limit=post_limit):
        if strict_filter:
            if keyword.lower() in submission.title.lower() or keyword.lower() in submission.selftext.lower():
                top_posts.append([submission.title, submission.score, submission.url, submission.created_utc])
        else:
            top_posts.append([submission.title, submission.score, submission.url, submission.created_utc])
       
        if len(top_posts) >= post_limit:
            break
    df = pd.DataFrame(top_posts, columns=['Title', 'Score', 'URL', 'Created'])
    df['Created'] = pd.to_datetime(df['Created'], unit='s')
    return df







async def analyze_bulk_sentiment_and_summary(df, subreddit_name, keyword):
    text_block = "\n".join([f"- {title}" for title in df['Title']])
    prompt = (
        f"You are analyzing Reddit discussions from {subreddit_name} about the product '{keyword}'.\n\n"
        f"Here are the post titles:\n{text_block}\n\n"
        f"1. Count how many posts are Positive, Negative, or Neutral.\n"
        f"2. Write a brief summary of how users feel.\n"
        f"Respond in this format:\n"
        f"Positive: X\nNegative: Y\nNeutral: Z\n\nSummary: <your summary here>"
    )
    try:
        response = await model.generate_content_async(prompt)
        return response.text
    except Exception as e:
            error_msg = str(e)
            if "429" in error_msg:
                # Try to extract retry delay from Gemini's error message
                retry_seconds = 60  # Default fallback
                match = re.search(r"retry_delay\s*{\s*seconds:\s*(\d+)", error_msg)
                if match:
                    retry_seconds = int(match.group(1))
                print(f"Rate limit hit. Waiting {retry_seconds} seconds before retrying...")
                time.sleep(retry_seconds)
            else:
                return f"Error from Gemini: {e}"
    return "Error from Gemini: Rate limit hit repeatedly."












def analyze_quality(text_block, subreddit_name, keyword):
    prompt = (
        f"You are a professional quality control engineer and product manager at {subreddit_name}. \n"
        f"In 3-5 sentences, analyze the following Reddit post titles about '{keyword}' and provide a detailed analysis of the product quality. "
        f"Use a casual but professional tone, remembering this is the summary you will orally provide stakeholders and higher ups:\n\n{text_block}"
    )
    try:
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
            error_msg = str(e)
            if "429" in error_msg:
                # Try to extract retry delay from Gemini's error message
                retry_seconds = 60  # Default fallback
                match = re.search(r"retry_delay\s*{\s*seconds:\s*(\d+)", error_msg)
                if match:
                    retry_seconds = int(match.group(1))
                print(f"Rate limit hit. Waiting {retry_seconds} seconds before retrying...")
                time.sleep(retry_seconds)
            else:
                return f"Error from Gemini: {e}"
    return "Error from Gemini: Rate limit hit repeatedly."












async def full_analysis(subreddit_name, keyword, post_limit):
    df = get_top_opinions(subreddit_name, post_limit, keyword)
    if df.empty:
        return "No opinions found.", df, None, "", ""




















    # One bulk Gemini call
    gemini_output = await analyze_bulk_sentiment_and_summary(df, subreddit_name, keyword)








    # Parse Gemini output
    try:
        pos = int(re.search(r'Positive:\s*(\d+)', gemini_output).group(1))
        neg = int(re.search(r'Negative:\s*(\d+)', gemini_output).group(1))
        neu = int(re.search(r'Neutral:\s*(\d+)', gemini_output).group(1))
        summary = re.search(r'Summary:\s*(.*)', gemini_output, re.DOTALL).group(1).strip()
    except:
        pos, neg, neu = 0, 0, 0
        summary = gemini_output








    # Sentiment label
    if pos > max(neg, neu):
        overall = "positive"
    elif neg > max(pos, neu):
        overall = "negative"
    else:
        overall = "neutral"




    sentiment_df = pd.DataFrame({
        "Sentiment": ["Positive", "Negative", "Neutral"],
        "Count": [pos, neg, neu]
    })




    product_quality = analyze_quality(summary, subreddit_name, keyword)








    score_summary = (
        f"### General opinions on '{keyword}' from {subreddit_name}:\n"
        f"- **Positive Posts**: {pos}\n"
        f"- **Negative Posts**: {neg}\n"
        f"- **Neutral Posts**: {neu}\n\n"
        f"💬 **Overall, the sentiment is _{overall}_**."
    )
    return score_summary, df, sentiment_df, summary, product_quality








# --- MAIN ACTION ---
if st.button('Start Eavesdropping'):
    location_label = "on Reddit" if subreddit_name == "all" else f"on {subreddit_name}"
    st.write(f"### Listening in on what people are saying about **{keyword}** {location_label}...")









    with st.spinner('Snooping around...'):
        summary, posts_df, sentiment_df, brand_summary, product_quality = asyncio.run(
            full_analysis(subreddit_name, keyword, post_limit)
        )




    if posts_df.empty:
        st.warning("No relevant posts found.")
    else:
        st.markdown("## What’s the Word?")
        st.write(brand_summary)
        st.markdown("## Product Quality")
        st.write(product_quality)




        st.markdown("## Sentiment Scorecard")








        def get_sentiment_label(score):
            if score >= 90:
                return "Excellent"
            elif score >= 75:
                return "Very Positive"
            elif score >= 60:
                return "Positive"
            elif 45 <= score <= 60:
                return "Mixed"
            elif score >= 30:
                return "Negative"
            elif score >= 15:
                return "Very Negative"
            else:
                return "Critical"




        total_posts = sentiment_df['Count'].sum()
        sentiment_score = (
            sentiment_df[sentiment_df['Sentiment'] == 'Positive']['Count'].sum() * 1.0 +
            sentiment_df[sentiment_df['Sentiment'] == 'Neutral']['Count'].sum() * 0.5
        )
        sentiment_percent = round((sentiment_score / total_posts) * 100, 1)
        letter_grade = get_sentiment_label(sentiment_percent)




        ##displaying a large percentage and letter grade
        st.markdown(
            f"""
            <div style="display: flex; flex-direction: column; align-items: center; justify-content: center; height: 66vh;">
                <div style="font-size: 15vw; font-weight: bold; color: #00000;">
                    {sentiment_percent}%
                </div>
                <div style="font-size: 4vw; font-weight: semi-bold; color: #333;">
                    Grade: {letter_grade}
                </div>
                <div style="font-size: 1.5vw; color: #666;">
                    {subreddit_name} on "{keyword}"
                </div>
            </div>
            """,
            unsafe_allow_html=True
        )








        st.markdown("## Sentiment Breakdown")
        st.markdown(summary)








        chart = alt.Chart(sentiment_df).mark_bar().encode(
            x=alt.X('Sentiment', sort=None),
            y='Count',
            color='Sentiment'
        ).properties(width=400, height=300)








        st.altair_chart(chart, use_container_width=True)




        st.markdown("## Top Posts")
        for _, row in posts_df.iterrows():
            st.markdown(f"**[{row['Title']}]({row['URL']})**")
            st.markdown(f" Score: {row['Score']} |  {row['Created'].strftime('%Y-%m-%d')}")
            st.write("---")




# --- FOOTER ---
st.write("---")
st.caption("BrandWhispers: AI-powered brand eavesdropping for product people and cultural sleuths.")










# Adding footer logo (no changes needed)
def add_footer_logo(png_file_path):
    # Encode image to base64
    with open(png_file_path, "rb") as f:
        data = f.read()
    encoded = base64.b64encode(data).decode()


    # HTML for the footer
    footer_html = f"""
<div style="position: fixed; bottom: 10px; width: 100%; text-align: center; z-index: 1000; background-color: rgba(255,255,255,0);">
    <img src="data:image/png;base64,{encoded}" alt="logo" height="90">
</div>
"""
    st.markdown(footer_html, unsafe_allow_html=True)


# Call the function with your image filename
add_footer_logo("RedditProjectBrandAssets.png")