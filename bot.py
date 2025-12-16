import os
import random
import argparse
import sys
from datetime import datetime, timezone
import time
import tweepy
import google.generativeai as genai
import io
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


def retry_api_call(func, max_retries=3, delay=2):
    """Retry wrapper for API calls."""
    for attempt in range(max_retries):
        try:
            return func()
        except Exception as e:
            if attempt == max_retries - 1:
                raise e
            print(f"Attempt {attempt + 1} failed: {e}. Retrying in {delay}s...")
            time.sleep(delay)
            delay *= 2


def get_active_campaign(supabase: Client, campaign_name: str = None):
    """Fetch the active campaign from the database."""
    try:
        query = supabase.table("campaigns").select("*").eq("active", True)
        if campaign_name:
            query = query.eq("name", campaign_name)
        response = query.limit(1).execute()
        return response.data[0] if response.data else None
    except Exception as e:
        print(f"Error fetching campaign: {e}")
        return None


def generate_content(supabase: Client, campaign_data=None, campaign_description: str = None):
    """Generate tweet text and image prompt using Gemini."""
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
        system_prompt = f"You are a social media manager. Your goal is to create engaging content about: {campaign_description}"
        topic = campaign_description
    else:
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
        response = retry_api_call(lambda: model.generate_content(prompt))
        text_lines = [line.strip() for line in response.text.strip().split('\n') if line.strip()]
        
        tweet_text = text_lines[0].replace("Tweet:", "").strip() if len(text_lines) >= 1 else ""
        image_prompt = text_lines[1].replace("Image Prompt:", "").strip() if len(text_lines) >= 2 else ""
        
        if not tweet_text:
            tweet_text = "Check out our latest updates! #tech"
        if not image_prompt:
            image_prompt = "A modern tech background with abstract nodes."
            
        if len(tweet_text) > 280:
            tweet_text = tweet_text[:277] + "..."
        
        # Log generated content to Supabase
        try:
            supabase.table("logs").insert({
                "message": f"Generated content - Topic: {topic}",
                "level": "INFO"
            }).execute()
        except Exception as log_err:
            print(f"Failed to log content generation: {log_err}")
            
        return tweet_text, image_prompt
    except Exception as e:
        print(f"Error generating content: {e}")
        raise e


def run_bot(dry_run=False, campaign_name: str = None):
    """Main execution flow."""
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
    
    try:
        print("Starting bot run...")
        
        campaign = get_active_campaign(supabase, campaign_name) if campaign_name else get_active_campaign(supabase)

        campaign_id_to_log = None
        
        if campaign:
            print(f"Active Campaign: {campaign.get('name')}")
            tweet_text, image_prompt = generate_content(supabase, campaign_data=campaign)
            campaign_id_to_log = campaign.get('id')
        elif campaign_name:
            print(f"No active campaign found matching '{campaign_name}'. Generating ad-hoc content.")
            tweet_text, image_prompt = generate_content(supabase, campaign_description=campaign_name)
        else:
            print("No active campaign found. Generating general content.")
            tweet_text, image_prompt = generate_content(supabase)
        
        print(f"Generated Tweet: {tweet_text}")
        print(f"Image Prompt: {image_prompt}")

        # Image Generation
        image_bytes = None
        media_id = None
        
        if image_prompt:
            print("Attempting to generate image...")
            try:
                genai.configure(api_key=GEMINI_API_KEY)
                image_model_name = "gemini-2.0-flash-exp-image-generation"

                print(f"Using SDK for {image_model_name}...")
                image_model = genai.GenerativeModel(image_model_name)
                
                result = retry_api_call(lambda: image_model.generate_content(image_prompt))
                
                if result and result.parts:
                    for part in result.parts:
                        if part.inline_data:
                            image_bytes = part.inline_data.data
                            break
                
                if image_bytes:
                    print("Image generated successfully.")
                    if dry_run:
                        with open("dry_run_image.png", "wb") as f:
                            f.write(image_bytes)
                        print("[DRY RUN] Saved generated image to 'dry_run_image.png'")
                else:
                    response_text = getattr(result, 'text', None)
                    print(f"Model did not return image data. Response: {response_text[:100] if response_text else 'No text'}...")

            except Exception as img_err:
                print(f"Image generation failed: {img_err}. Proceeding with text only.")
                try:
                    supabase.table("logs").insert({
                        "message": f"Image generation failed: {img_err}",
                        "level": "WARNING"
                    }).execute()
                except:
                    pass

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

        # Upload Media
        if image_bytes:
            print("Uploading image to X...")
            try:
                auth = tweepy.OAuth1UserHandler(
                    X_API_KEY, X_API_SECRET,
                    X_ACCESS_TOKEN, X_ACCESS_TOKEN_SECRET
                )
                api = tweepy.API(auth)
                media = retry_api_call(lambda: api.media_upload(filename="image.png", file=io.BytesIO(image_bytes)))
                media_id = media.media_id
                print(f"Image uploaded. Media ID: {media_id}")
            except Exception as upload_err:
                print(f"Media upload failed: {upload_err}. Posting text only.")

        # Post Tweet
        print("Posting to X...")
        try:
            if media_id:
                response = retry_api_call(lambda: client.create_tweet(text=tweet_text, media_ids=[media_id]))
            else:
                response = retry_api_call(lambda: client.create_tweet(text=tweet_text))
            
            post_id = response.data['id']
            print(f"Posted! ID: {post_id}")
            
            # Log to Supabase
            try:
                post_data = {
                    "campaign_id": campaign_id_to_log, 
                    "content": tweet_text,
                    "x_post_id": post_id,
                    "posted_at": datetime.now(timezone.utc).isoformat()
                }
                supabase.table("posts").insert(post_data).execute()
                print("Logged to database.")
            except Exception as db_err:
                print(f"Failed to log post to database: {db_err}")
            
        except Exception as post_err:
            print(f"Posting failed: {post_err}")
            raise post_err

    except Exception as e:
        error_msg = f"Bot failed: {str(e)}"
        print(error_msg)
        try:
            log_client: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
            log_client.table("logs").insert({"message": error_msg, "level": "ERROR"}).execute()
        except Exception as log_error:
            print(f"Failed to log error to DB: {log_error}")


def add_campaign():
    """Interactive campaign creation."""
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
    
    print("\n=== Add New Campaign ===")
    name = input("Campaign name: ").strip()
    if not name:
        print("Name is required.")
        return
    
    system_prompt = input("System prompt (how should AI behave): ").strip()
    topics_input = input("Topics (comma-separated): ").strip()
    topic_list = [t.strip() for t in topics_input.split(",") if t.strip()] or ["General update"]
    
    active = input("Activate now? (y/n): ").strip().lower() == 'y'
    
    try:
        supabase.table("campaigns").insert({
            "name": name,
            "system_prompt": system_prompt or "Write a professional tweet.",
            "topic_list": topic_list,
            "active": active
        }).execute()
        print(f"Campaign '{name}' added successfully!")
    except Exception as e:
        print(f"Failed to add campaign: {e}")


def list_campaigns():
    """List all campaigns."""
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
    try:
        response = supabase.table("campaigns").select("id, name, active").execute()
        if not response.data:
            print("No campaigns found.")
            return
        print("\n=== Campaigns ===")
        for c in response.data:
            status = "✓ Active" if c['active'] else "✗ Inactive"
            print(f"  [{c['id']}] {c['name']} - {status}")
    except Exception as e:
        print(f"Failed to list campaigns: {e}")


def toggle_campaign(campaign_id: int):
    """Toggle campaign active status."""
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
    try:
        response = supabase.table("campaigns").select("active").eq("id", campaign_id).execute()
        if not response.data:
            print(f"Campaign {campaign_id} not found.")
            return
        current_status = response.data[0]['active']
        new_status = not current_status
        supabase.table("campaigns").update({"active": new_status}).eq("id", campaign_id).execute()
        print(f"Campaign {campaign_id} is now {'active' if new_status else 'inactive'}.")
    except Exception as e:
        print(f"Failed to toggle campaign: {e}")


def generate_reply(mention_text: str, author_username: str) -> str:
    """Generate a contextual reply using Gemini."""
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel('gemini-2.5-flash')
    
    # Account for @username prefix in reply (username + @ + space)
    max_reply_len = 280 - len(author_username) - 2
    
    prompt = f"""You are a helpful social media assistant. Someone mentioned you with this tweet:

Author: @{author_username}
Tweet: {mention_text}

Write a friendly, helpful reply under {max_reply_len} characters. Be conversational and address their question or comment directly. Don't use hashtags unless relevant. Don't start with "Hey" or "Hi" every time - vary your openings."""

    try:
        response = retry_api_call(lambda: model.generate_content(prompt))
        reply = response.text.strip()
        
        # Clean up any quotes the model might add
        if reply.startswith('"') and reply.endswith('"'):
            reply = reply[1:-1]
        
        if len(reply) > max_reply_len:
            reply = reply[:max_reply_len - 3] + "..."
        
        return reply
    except Exception as e:
        print(f"Error generating reply: {e}")
        return None


def is_mention_processed(supabase: Client, mention_id: str) -> bool:
    """Check if mention has already been processed."""
    try:
        response = supabase.table("mentions").select("id").eq("mention_id", mention_id).execute()
        return len(response.data) > 0
    except Exception as e:
        print(f"Error checking mention status: {e}")
        # Return True on error to avoid duplicate replies
        return True


def run_mentions_bot(dry_run=False, limit=5):
    """Fetch and reply to mentions."""
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
    
    print("Starting mentions bot...")
    
    # Authenticate
    client = tweepy.Client(
        consumer_key=X_API_KEY,
        consumer_secret=X_API_SECRET,
        access_token=X_ACCESS_TOKEN,
        access_token_secret=X_ACCESS_TOKEN_SECRET,
        wait_on_rate_limit=True
    )
    
    try:
        # Get authenticated user ID
        me = client.get_me()
        if not me.data:
            print("Failed to get authenticated user.")
            return
        
        user_id = me.data.id
        username = me.data.username
        print(f"Authenticated as @{username} (ID: {user_id})")
        
        # X API v2 requires max_results between 5-100
        api_limit = max(5, min(limit, 100))
        
        # Fetch recent mentions
        mentions = retry_api_call(lambda: client.get_users_mentions(
            id=user_id,
            max_results=api_limit,
            tweet_fields=["created_at", "author_id", "conversation_id"],
            expansions=["author_id"]
        ))
        
        if not mentions.data:
            print("No mentions found.")
            return
        
        # Build author lookup
        authors = {u.id: u.username for u in (mentions.includes.get('users', []) if mentions.includes else [])}
        
        processed = 0
        for mention in mentions.data:
            if processed >= limit:
                break
                
            mention_id = str(mention.id)
            author_id = mention.author_id
            
            # Skip self-mentions
            if author_id == user_id:
                print(f"Skipping self-mention: {mention_id}")
                continue
            
            # Skip if already processed
            if is_mention_processed(supabase, mention_id):
                print(f"Skipping already processed mention: {mention_id}")
                continue
            
            author_username = authors.get(author_id, "user")
            mention_text = mention.text
            
            # Remove our @username from the text for cleaner context
            clean_text = mention_text.replace(f"@{username}", "").strip()
            
            print(f"\nMention from @{author_username}: {clean_text[:50]}...")
            
            # Generate reply
            reply_text = generate_reply(clean_text, author_username)
            if not reply_text:
                print("Failed to generate reply, skipping.")
                continue
            
            print(f"Generated reply: {reply_text}")
            
            # Prepare full reply text
            full_reply = f"@{author_username} {reply_text}"
            
            if dry_run:
                print("[DRY RUN] Would reply to this mention.")
                # Log to DB even in dry run to prevent reprocessing
                try:
                    supabase.table("mentions").insert({
                        "mention_id": mention_id,
                        "author_username": author_username,
                        "mention_text": mention_text,
                        "reply_text": reply_text,
                        "reply_id": "DRY_RUN",
                        "replied_at": datetime.now(timezone.utc).isoformat()
                    }).execute()
                except:
                    pass
                processed += 1
            else:
                try:
                    # Post reply - use default args to capture current values
                    def make_tweet(text=full_reply, reply_to=mention_id):
                        return client.create_tweet(text=text, in_reply_to_tweet_id=reply_to)
                    
                    response = retry_api_call(make_tweet)
                    reply_id = response.data['id']
                    print(f"Replied! ID: {reply_id}")
                    
                    # Log to database
                    supabase.table("mentions").insert({
                        "mention_id": mention_id,
                        "author_username": author_username,
                        "mention_text": mention_text,
                        "reply_text": reply_text,
                        "reply_id": reply_id,
                        "replied_at": datetime.now(timezone.utc).isoformat()
                    }).execute()
                    
                    processed += 1
                    
                except Exception as reply_err:
                    print(f"Failed to reply: {reply_err}")
                    try:
                        supabase.table("logs").insert({
                            "message": f"Failed to reply to mention {mention_id}: {reply_err}",
                            "level": "ERROR"
                        }).execute()
                    except:
                        pass
        
        print(f"\nProcessed {processed} mentions.")
        
    except Exception as e:
        error_msg = f"Mentions bot failed: {str(e)}"
        print(error_msg)
        try:
            supabase.table("logs").insert({"message": error_msg, "level": "ERROR"}).execute()
        except:
            pass


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the X Marketing Bot")
    parser.add_argument("--test", action="store_true", help="Run in dry-run mode (no posting)")
    parser.add_argument("--campaign", type=str, help="Name of the specific campaign to run")
    parser.add_argument("--add", action="store_true", help="Add a new campaign")
    parser.add_argument("--list", action="store_true", help="List all campaigns")
    parser.add_argument("--toggle", type=int, help="Toggle campaign active status by ID")
    parser.add_argument("--mentions", action="store_true", help="Process and reply to mentions")
    parser.add_argument("--limit", type=int, default=5, help="Max mentions to process (default: 5)")
    args = parser.parse_args()

    if args.add:
        add_campaign()
    elif args.list:
        list_campaigns()
    elif args.toggle:
        toggle_campaign(args.toggle)
    elif args.mentions:
        limit = max(1, args.limit)  # Ensure at least 1
        run_mentions_bot(dry_run=args.test, limit=limit)
    else:
        campaign_input = args.campaign
        if not campaign_input and sys.stdin.isatty():
            user_input = input("Enter campaign name (or press Enter to run any active campaign): ").strip()
            if user_input:
                campaign_input = user_input
        run_bot(dry_run=args.test, campaign_name=campaign_input)
