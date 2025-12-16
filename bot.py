import os
import random
import argparse
from datetime import datetime, timezone
import tweepy
import google.generativeai as genai
from supabase import create_client, Client
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configuration
X_API_KEY = os.getenv("X_API_KEY")
X_API_SECRET = os.getenv("X_API_SECRET")
X_ACCESS_TOKEN = os.getenv("X_ACCESS_TOKEN")
X_ACCESS_TOKEN_SECRET = os.getenv("X_ACCESS_TOKEN_SECRET")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

# Validate critical environment variables
REQUIRED_VARS = [
    "X_API_KEY", "X_API_SECRET", "X_ACCESS_TOKEN", "X_ACCESS_TOKEN_SECRET",
    "GEMINI_API_KEY", "SUPABASE_URL", "SUPABASE_KEY"
]
missing_vars = [var for var in REQUIRED_VARS if not os.getenv(var)]
if missing_vars:
    raise EnvironmentError(f"Missing required environment variables: {', '.join(missing_vars)}")

def get_active_campaign(supabase: Client):
    """Fetch the first active campaign from the database."""
    try:
        response = supabase.table("campaigns").select("*").eq("active", True).limit(1).execute()
        if response.data:
            return response.data[0]
        return None
    except Exception as e:
        print(f"Error fetching campaign: {e}")
        return None

def generate_content(campaign):
    """Generate tweet text and image prompt using Gemini."""
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel('gemini-2.5-flash')
    
    topic_list = campaign.get('topic_list')
    if not topic_list or not isinstance(topic_list, list):
        topic_list = ["General update"]
        
    topic = random.choice(topic_list)
    system_prompt = campaign.get('system_prompt', "Write a professional tweet.")
    
    prompt = f"""
    You are a social media manager.
    Topic: {topic}
    Campaign Goal: {system_prompt}
    
    Output exactly two lines:
    Line 1: The tweet text (under 280 characters).
    Line 2: A comprehensive image prompt to generate a visual for this tweet.
    Do not add any labels like 'Tweet:' or 'Image Prompt:'. Just the content.
    """
    
    try:
        response = model.generate_content(prompt)
        text_lines = [line.strip() for line in response.text.strip().split('\n') if line.strip()]
        
        tweet_text = ""
        image_prompt = ""

        if len(text_lines) >= 1:
            tweet_text = text_lines[0].replace("Tweet:", "").strip()
        if len(text_lines) >= 2:
            image_prompt = text_lines[1].replace("Image Prompt:", "").strip()
        
        # Fallback if parsing fails or returns empty
        if not tweet_text:
            tweet_text = "Check out our latest updates! #tech"
        if not image_prompt:
            image_prompt = "A modern tech background with abstract nodes."
            
        # Hard truncate to 280 characters to satisfy X API limits
        if len(tweet_text) > 280:
            tweet_text = tweet_text[:277] + "..."
            
        return tweet_text, image_prompt
    except Exception as e:
        print(f"Error generating content: {e}")
        raise e

def run_bot(dry_run=False):
    """Main execution flow."""
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
    
    try:
        print("Starting bot run...")
        campaign = get_active_campaign(supabase)
        if not campaign:
            print("No active campaign found.")
            return

        print(f"Active Campaign: {campaign.get('name')}")
        tweet_text, image_prompt = generate_content(campaign)
        
        print(f"Generated Tweet: {tweet_text}")
        print(f"Image Prompt: {image_prompt}")

        # TODO: Implement image generation using an image model (e.g., Imagen)
        # and attach the media_id to the tweet.
        if image_prompt:
            print("Notice: Image generation is not yet implemented. This will be a text-only tweet.")

        if dry_run:
            print("[DRY RUN] Skipping posting to X and database logging.")
            return

        # Authenticate with X
        client = tweepy.Client(
            consumer_key=X_API_KEY,
            consumer_secret=X_API_SECRET,
            access_token=X_ACCESS_TOKEN,
            access_token_secret=X_ACCESS_TOKEN_SECRET
        )

        # Post Tweet
        print("Posting to X...")
        response = client.create_tweet(text=tweet_text)
        post_id = response.data['id']
        print(f"Posted! ID: {post_id}")

        # Log to Supabase
        post_data = {
            "campaign_id": campaign.get('id'),
            "content": tweet_text,
            "x_post_id": post_id,
            "posted_at": datetime.now(timezone.utc).isoformat()
        }
        supabase.table("posts").insert(post_data).execute()
        print("Logged to database.")

    except Exception as e:
        error_msg = f"Bot failed: {str(e)}"
        print(error_msg)
        # Log error
        try:
            # Re-initialize client locally to avoid using a potentially broken client instance
            log_client: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
            log_client.table("logs").insert({"message": error_msg, "level": "ERROR"}).execute()
        except Exception as log_error:
            print(f"Failed to log error to DB: {log_error}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the X Marketing Bot")
    parser.add_argument("--test", action="store_true", help="Run in dry-run mode (no posting)")
    args = parser.parse_args()
    
    run_bot(dry_run=args.test)
