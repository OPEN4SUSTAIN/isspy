import os
import json
import urllib.request
import urllib.error
from datetime import datetime, timezone

TOKEN = os.environ["GH_TOKEN"]
STATE_FILE = "state.json"

def gh(path):
    req = urllib.request.Request(
        f"https://api.github.com{path}",
        headers={
            "Authorization": f"Bearer {TOKEN}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28"
        }
    )
    with urllib.request.urlopen(req) as res:
        return json.loads(res.read())

def get_all_forks():
    forks, page = [], 1
    while True:
        repos = gh(f"/user/repos?type=forks&per_page=100&page={page}")
        if not repos:
            break
        forks.extend(repos)
        if len(repos) < 100:
            break
        page += 1
    return forks

def get_collaborators(owner, repo):
    try:
        collaborators = gh(f"/repos/{owner}/{repo}/collaborators?per_page=100")
        return {c["login"] for c in collaborators}
    except urllib.error.HTTPError as e:
        if e.code in (404, 403):
            return set()
        raise

def get_new_issues(owner, repo, since):
    try:
        issues = gh(f"/repos/{owner}/{repo}/issues?state=open&since={since}&per_page=50")
        return [i for i in issues if "pull_request" not in i]
    except urllib.error.HTTPError as e:
        if e.code in (404, 403):
            return []
        raise

def create_issue(title, body):
    repo_owner = os.environ.get("GITHUB_REPOSITORY_OWNER", "Demiserular")
    repo_name = os.environ.get("GITHUB_REPOSITORY_NAME", "isspy")
    if "/" in os.environ.get("GITHUB_REPOSITORY", ""):
        repo_owner, repo_name = os.environ["GITHUB_REPOSITORY"].split("/")
    
    req = urllib.request.Request(
        f"https://api.github.com/repos/{repo_owner}/{repo_name}/issues",
        data=json.dumps({"title": title, "body": body}).encode(),
        headers={
            "Authorization": f"Bearer {TOKEN}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28"
        },
        method="POST"
    )
    with urllib.request.urlopen(req) as res:
        return json.loads(res.read())

def get_issues():
    repo_owner = os.environ.get("GITHUB_REPOSITORY_OWNER", "Demiserular")
    repo_name = os.environ.get("GITHUB_REPOSITORY_NAME", "isspy")
    if "/" in os.environ.get("GITHUB_REPOSITORY", ""):
        repo_owner, repo_name = os.environ["GITHUB_REPOSITORY"].split("/")
    
    try:
        issues = gh(f"/repos/{repo_owner}/{repo_name}/issues?state=open&per_page=100")
        return [i for i in issues if i["title"].startswith("ISSPY report -")]
    except urllib.error.HTTPError as e:
        if e.code in (404, 403):
            return []
        raise

def close_issue(issue_number):
    repo_owner = os.environ.get("GITHUB_REPOSITORY_OWNER", "Demiserular")
    repo_name = os.environ.get("GITHUB_REPOSITORY_NAME", "isspy")
    if "/" in os.environ.get("GITHUB_REPOSITORY", ""):
        repo_owner, repo_name = os.environ["GITHUB_REPOSITORY"].split("/")
    
    req = urllib.request.Request(
        f"https://api.github.com/repos/{repo_owner}/{repo_name}/issues/{issue_number}",
        data=json.dumps({"state": "closed"}).encode(),
        headers={
            "Authorization": f"Bearer {TOKEN}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28"
        },
        method="PATCH"
    )
    with urllib.request.urlopen(req) as res:
        return json.loads(res.read())

def main():
    state = {}
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE) as f:
            state = json.load(f)

    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    now_dt = datetime.now(timezone.utc)
    now_readable = now_dt.strftime("%B %d, %Y at %H:%M UTC")
    
    # Close issues older than 2 days
    issues = get_issues()
    for issue in issues:
        created_at = datetime.fromisoformat(issue["created_at"].replace("Z", "+00:00"))
        age_days = (now_dt - created_at).days
        if age_days >= 2:
            try:
                close_issue(issue["number"])
                print(f"Closed issue #{issue['number']} (age: {age_days} days)")
            except Exception as e:
                print(f"Failed to close issue #{issue['number']}: {e}")
    
    forks = get_all_forks()

    lines = [f"# isspy report", f"**Run:** {now} | **Forks scanned:** {len(forks)}\n"]
    found_any = False

    for fork in forks:
        parent = fork.get("parent")
        if not parent:
            try:
                full = gh(f"/repos/{fork['full_name']}")
                parent = full.get("parent")
            except Exception:
                continue
        if not parent:
            continue

        upstream = parent["full_name"]
        since = state.get(upstream, "2024-01-01T00:00:00Z")
        collaborators = get_collaborators(parent["owner"]["login"], parent["name"])
        new_issues = get_new_issues(parent["owner"]["login"], parent["name"], since)

        if new_issues:
            found_any = True
            lines.append(f"## [{upstream}](https://github.com/{upstream})")
            lines.append(f"*{len(new_issues)} new issue(s)*\n")
            for i in new_issues:
                created_at = i['created_at'].replace('T', ' ').replace('Z', ' UTC')
                obfuscated_url = i['html_url'].replace("github.com", "github\u200b.com")
                is_maintainer = i["user"]["login"] in collaborators
                tag = " **[M]**" if is_maintainer else ""
                lines.append(
                    f"- Issue {i['number']}: {i['title']}{tag} - [{obfuscated_url}](https://href.li/?{i['html_url']}) - *{created_at}*"
                )
            lines.append("")

        state[upstream] = now

    if not found_any:
        lines.append("_No new issues in any upstream repo._")

    report = "\n".join(lines)
    print(report)

    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a") as f:
            f.write(report)

    if found_any:
        try:
            create_issue(f"ISSPY report - {now_readable}", report)
        except Exception as e:
            print(f"Failed to create issue: {e}")

    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)

if __name__ == "__main__":
    main()
