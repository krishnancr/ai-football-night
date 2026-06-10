#!/usr/bin/env python3
"""
Post a Twitter thread from a JSON thread file.
Usage:
  python distribute.py runs/wc_brazil-croatia_20260611_thread.json
  python distribute.py runs/wc_brazil-croatia_20260611_thread.json --dry-run
"""
import json
import os
import sys
from pathlib import Path

import tweepy
from dotenv import load_dotenv

load_dotenv()


def post_twitter_thread(tweets: list, dry_run: bool = False) -> list:
    """
    Post a list of tweet strings as a thread.
    Returns list of posted tweet IDs (empty if dry_run).
    """
    if dry_run:
        print("\n[DRY RUN] Would post this thread:")
        for i, tweet in enumerate(tweets, 1):
            print(f"\n--- Tweet {i}/{len(tweets)} ({len(tweet)} chars) ---")
            print(tweet)
        return []

    client = tweepy.Client(
        consumer_key=os.getenv("TWITTER_API_KEY"),
        consumer_secret=os.getenv("TWITTER_API_SECRET"),
        access_token=os.getenv("TWITTER_ACCESS_TOKEN"),
        access_token_secret=os.getenv("TWITTER_ACCESS_SECRET"),
    )

    tweet_ids = []
    prev_id = None

    for i, tweet_text in enumerate(tweets, 1):
        print(f"Posting tweet {i}/{len(tweets)}...")
        kwargs = {"text": tweet_text}
        if prev_id:
            kwargs["in_reply_to_tweet_id"] = prev_id

        response = client.create_tweet(**kwargs)
        tweet_id = response.data["id"]
        tweet_ids.append(tweet_id)
        prev_id = tweet_id
        print(f"  Posted: {tweet_id}")

    return tweet_ids


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("thread_file", help="Path to *_thread.json file")
    parser.add_argument("--dry-run", action="store_true", help="Print tweets without posting")
    args = parser.parse_args()

    thread_path = Path(args.thread_file)
    if not thread_path.exists():
        print(f"Error: {thread_path} not found")
        sys.exit(1)

    tweets = json.loads(thread_path.read_text())
    if not isinstance(tweets, list):
        print("Error: thread file must be a JSON array of strings")
        sys.exit(1)

    tweet_ids = post_twitter_thread(tweets, dry_run=args.dry_run)

    if tweet_ids:
        print(f"\nThread posted. First tweet: https://twitter.com/i/web/status/{tweet_ids[0]}")


if __name__ == "__main__":
    main()
