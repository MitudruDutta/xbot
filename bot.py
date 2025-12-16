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

def get_active_campaign(supabase: Client, campaign_name: str = None):
    """Fetch the active campaign from the database.
    
    If campaign_name is provided, it fetches that specific active campaign.
    Otherwise, it fetches the first active campaign found.
    """
    try:
        query = supabase.table("campaigns").select("*").eq("active", True)
        
        if campaign_name:
            query = query.eq("name", campaign_name)
            
        response = query.limit(1).execute()
        if response.data:
            return response.data[0]
        return None
    except Exception as e:
        print(f"Error fetching campaign: {e}")
        return None

def generate_content(supabase: Client, campaign_data=None, campaign_description: str = None):
    """Generate tweet text and image prompt using Gemini.
    
    Can generate content from a Supabase campaign object or a free-form description.
    """
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel('gemini-2.5-flash')
    
    topic = "General update"
    system_prompt = "Write a professional tweet."
    
    if campaign_data:
        topic_list = campaign_data.get('topic_list')
        if not topic_list or not isinstance(topic_list, list):
            topic_list = ["General update"]
        topic = random.choice(topic_list)
        system_prompt = campaign_data.get('system_prompt', system_prompt)
    elif campaign_description:
        # For ad-hoc campaigns, the description itself becomes the primary goal/topic
        system_prompt = f"You are a social media manager. Your goal is to create engaging content about: {campaign_description}"
        topic = campaign_description # Use the description as the topic for consistency
    else:
        # Fallback if neither is provided
        system_prompt = "You are a social media manager. Write a professional tweet about a general topic."

    prompt = f"""
    {system_prompt}
    Topic: {topic}
    
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

def run_bot(dry_run=False, campaign_name: str = None):
    """Main execution flow."""
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
    
    try:
        print("Starting bot run...")
        
        campaign = None
        if campaign_name:
            campaign = get_active_campaign(supabase, campaign_name)

        tweet_text = ""
        image_prompt = ""
        campaign_id_to_log = None
        
        if campaign:
            print(f"Active Campaign: {campaign.get('name')}")
            tweet_text, image_prompt = generate_content(supabase, campaign_data=campaign)
            campaign_id_to_log = campaign.get('id')
        else:
            if campaign_name: # User provided a description, but it wasn't a stored campaign
                print(f"No active campaign found matching '{campaign_name}'. Generating ad-hoc content based on description.")
                tweet_text, image_prompt = generate_content(supabase, campaign_description=campaign_name)
            else: # No campaign name provided, no active campaign found
                print("No active campaign found. Generating general content.")
                tweet_text, image_prompt = generate_content(supabase) # Generate general content
        
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
            "campaign_id": campaign_id_to_log, # Use the determined campaign ID or None
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
    parser.add_argument("--campaign", type=str, help="Name of the specific campaign to run")
    args = parser.parse_args()

    campaign_input = args.campaign
    if not campaign_input:
        user_input = input("Enter campaign name (or press Enter to run any active campaign): ").strip()
        if user_input:
            campaign_input = user_input
    
    run_bot(dry_run=args.test, campaign_name=campaign_input)
