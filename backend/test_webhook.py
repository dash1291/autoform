#!/usr/bin/env python3
"""
Script to test webhook locally with your GitHub payload
"""
import json
import hmac
import hashlib
import requests

# Your GitHub payload
payload = {
  "ref": "refs/heads/main",
  "before": "ece2b3c4d8230ccba3ee38fe51460fb2a6bd897d",
  "after": "044271b69a2d9fdfe8f69373d15ecf5339f82e05",
  "repository": {
    "id": 989270667,
    "node_id": "R_kgDOOvcSiw",
    "name": "autoform",
    "full_name": "dash1291/autoform",
    "private": True,
    "owner": {
      "name": "dash1291",
      "email": "ashish.dubey91@gmail.com",
      "login": "dash1291",
      "id": 870428,
      "node_id": "MDQ6VXNlcjg3MDQyOA==",
      "avatar_url": "https://avatars.githubusercontent.com/u/870428?v=4",
      "gravatar_id": "",
      "url": "https://api.github.com/users/dash1291",
      "html_url": "https://github.com/dash1291",
      "followers_url": "https://api.github.com/users/dash1291/followers",
      "following_url": "https://api.github.com/users/dash1291/following{/other_user}",
      "gists_url": "https://api.github.com/users/dash1291/gists{/gist_id}",
      "starred_url": "https://api.github.com/users/dash1291/starred{/owner}{/repo}",
      "subscriptions_url": "https://api.github.com/users/dash1291/subscriptions",
      "organizations_url": "https://api.github.com/users/dash1291/orgs",
      "repos_url": "https://api.github.com/users/dash1291/repos",
      "events_url": "https://api.github.com/users/dash1291/events{/privacy}",
      "received_events_url": "https://api.github.com/users/dash1291/received_events",
      "type": "User",
      "user_view_type": "public",
      "site_admin": False
    },
    "html_url": "https://github.com/dash1291/autoform",
    "description": "A Heroku-like Platform-as-a-Service (PaaS) system that deploys applications to AWS ECS.",
    "fork": False,
    "url": "https://api.github.com/repos/dash1291/autoform",
    "clone_url": "https://github.com/dash1291/autoform.git",
    "created_at": 1748028380,
    "updated_at": "2025-06-28T06:12:26Z",
    "pushed_at": 1751098356,
    "git_url": "git://github.com/dash1291/autoform.git",
    "ssh_url": "git@github.com:dash1291/autoform.git",
    "svn_url": "https://github.com/dash1291/autoform",
    "homepage": "",
    "size": 696,
    "stargazers_count": 0,
    "watchers_count": 0,
    "language": "Python",
    "has_issues": True,
    "has_projects": True,
    "has_downloads": True,
    "has_wiki": True,
    "has_pages": False,
    "has_discussions": False,
    "forks_count": 0,
    "mirror_url": None,
    "archived": False,
    "disabled": False,
    "open_issues_count": 9,
    "license": None,
    "allow_forking": True,
    "is_template": False,
    "web_commit_signoff_required": False,
    "topics": [],
    "visibility": "private",
    "forks": 0,
    "open_issues": 9,
    "watchers": 0,
    "default_branch": "main",
    "stargazers": 0,
    "master_branch": "main"
  },
  "pusher": {
    "name": "dash1291",
    "email": "ashish.dubey91@gmail.com"
  },
  "sender": {
    "login": "dash1291",
    "id": 870428,
    "node_id": "MDQ6VXNlcjg3MDQyOA==",
    "avatar_url": "https://avatars.githubusercontent.com/u/870428?v=4",
    "gravatar_id": "",
    "url": "https://api.github.com/users/dash1291",
    "html_url": "https://github.com/dash1291",
    "type": "User",
    "user_view_type": "public",
    "site_admin": False
  },
  "created": False,
  "deleted": False,
  "forced": False,
  "base_ref": None,
  "compare": "https://github.com/dash1291/autoform/compare/ece2b3c4d823...044271b69a2d",
  "commits": [
    {
      "id": "044271b69a2d9fdfe8f69373d15ecf5339f82e05",
      "tree_id": "a6dca25024cead7a41fb99ea7857df9fbc69b60a",
      "distinct": True,
      "message": "add environment level status on project overview",
      "timestamp": "2025-06-28T13:42:31+05:30",
      "url": "https://github.com/dash1291/autoform/commit/044271b69a2d9fdfe8f69373d15ecf5339f82e05",
      "author": {
        "name": "Ashish Dubey",
        "email": "ashish.dubey91@gmail.com",
        "username": "dash1291"
      },
      "committer": {
        "name": "Ashish Dubey",
        "email": "ashish.dubey91@gmail.com",
        "username": "dash1291"
      },
      "added": [],
      "removed": [],
      "modified": [
        "backend/app/routers/environments.py",
        "backend/infrastructure/services/load_balancer_service.py",
        "frontend/src/app/projects/[id]/page.tsx",
        "frontend/src/lib/api.ts"
      ]
    }
  ],
  "head_commit": {
    "id": "044271b69a2d9fdfe8f69373d15ecf5339f82e05",
    "tree_id": "a6dca25024cead7a41fb99ea7857df9fbc69b60a",
    "distinct": True,
    "message": "add environment level status on project overview",
    "timestamp": "2025-06-28T13:42:31+05:30",
    "url": "https://github.com/dash1291/autoform/commit/044271b69a2d9fdfe8f69373d15ecf5339f82e05",
    "author": {
      "name": "Ashish Dubey",
      "email": "ashish.dubey91@gmail.com",
      "username": "dash1291"
    },
    "committer": {
      "name": "Ashish Dubey",
      "email": "ashish.dubey91@gmail.com",
      "username": "dash1291"
    },
    "added": [],
    "removed": [],
    "modified": [
      "backend/app/routers/environments.py",
      "backend/infrastructure/services/load_balancer_service.py",
      "frontend/src/app/projects/[id]/page.tsx",
      "frontend/src/lib/api.ts"
    ]
  }
}

def test_webhook(webhook_secret: str, server_url: str = "http://localhost:8000"):
    """Test the webhook with the provided payload"""
    
    # Convert payload to JSON string (GitHub format)
    payload_json = json.dumps(payload, separators=(',', ':'))
    payload_bytes = payload_json.encode('utf-8')
    
    # Generate signature
    signature = "sha256=" + hmac.new(
        webhook_secret.encode('utf-8'),
        payload_bytes,
        hashlib.sha256
    ).hexdigest()
    
    # Headers
    headers = {
        'Content-Type': 'application/json',
        'X-GitHub-Event': 'push',
        'X-Hub-Signature-256': signature,
        'X-GitHub-Delivery': 'a6c4a37c-53f7-11f0-939a-809b8bcf5722',
        'User-Agent': 'GitHub-Hookshot/2bbfd1f'
    }
    
    print(f"Testing webhook at: {server_url}/webhook/github")
    print(f"Signature: {signature}")
    print(f"Payload size: {len(payload_bytes)} bytes")
    print()
    
    try:
        response = requests.post(
            f"{server_url}/webhook/github",
            data=payload_bytes,
            headers=headers,
            timeout=30
        )
        
        print(f"Status Code: {response.status_code}")
        print(f"Response: {response.text}")
        
        if response.status_code == 200:
            print("✅ Webhook test successful!")
        else:
            print("❌ Webhook test failed!")
            
    except requests.exceptions.RequestException as e:
        print(f"❌ Request failed: {e}")

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) != 2:
        print("Usage: python test_webhook.py <webhook_secret>")
        print("Example: python test_webhook.py your-webhook-secret")
        sys.exit(1)
    
    webhook_secret = sys.argv[1]
    test_webhook(webhook_secret)