from flask import Flask, request, jsonify, render_template
import requests
from bs4 import BeautifulSoup
import openai
import anthropic
import os
import re
from urllib.parse import urljoin, urlparse
from dotenv import load_dotenv
import hashlib
from difflib import SequenceMatcher

load_dotenv()

app = Flask(__name__)

# API keys from environment variables
openai_api_key = os.getenv('OPENAI_API_KEY')
claude_api_key = os.getenv('CLAUDE_API_KEY')

@app.route('/')
def index():
    return render_template('index.html')

def fetch_page_text(page_url):
    try:
        response = requests.get(page_url, timeout=10)
        soup = BeautifulSoup(response.text, 'html.parser')
        for tag in soup(['script', 'style', 'noscript', 'header', 'footer', 'nav']):
            tag.decompose()
        texts = [element.get_text(' ', strip=True) for element in soup.find_all(['h1', 'h2', 'h3', 'p', 'li'])]
        return ' '.join(texts)
    except Exception:
        return ''


def scrape_website(url, max_pages=8):
    try:
        parsed_site = urlparse(url)
        base_domain = f"{parsed_site.scheme}://{parsed_site.netloc}"

        response = requests.get(url, timeout=10)
        soup = BeautifulSoup(response.text, 'html.parser')

        internal_links = set()
        for a in soup.find_all('a', href=True):
            href = a['href']
            if href.startswith('#'):
                continue
            absolute_link = urljoin(base_domain, href)
            parsed_link = urlparse(absolute_link)
            if parsed_link.netloc == parsed_site.netloc:
                cleaned = parsed_link.scheme + '://' + parsed_link.netloc + parsed_link.path
                internal_links.add(cleaned)

        page_texts = {}
        for idx, link in enumerate(sorted(internal_links)):
            if idx >= max_pages:
                break
            page_texts[link] = fetch_page_text(link)

        return {
            'links': sorted(internal_links),
            'page_texts': page_texts
        }
    except Exception:
        return {'links': [], 'page_texts': {}}


def calculate_similarity(text1, text2):
    """Calculate similarity between two texts (0-1 scale)"""
    if not text1 or not text2:
        return 0
    # Use SequenceMatcher to calculate similarity ratio
    return SequenceMatcher(None, text1.lower(), text2.lower()).ratio()

def is_duplicate_content(new_content, existing_contents, threshold=0.75):
    """Check if new content is too similar to existing content"""
    for location, existing_content in existing_contents.items():
        similarity = calculate_similarity(new_content[:500], existing_content[:500])
        if similarity > threshold:
            return True, location, similarity
    return False, None, 0


def bold_keywords(content, keywords):
    if not content or not keywords:
        return content
    keyword_list = [kw.strip() for kw in keywords.split(',') if kw.strip()]
    for keyword in keyword_list:
        escaped = re.escape(keyword)
        pattern = re.compile(rf'(?<!\*\*)(?<!\*)(\b{escaped}\b)(?!\*\*)(?!\*)', flags=re.IGNORECASE)
        content = pattern.sub(r'**\1**', content)
    return content


def get_content_hash(content):
    """Generate hash of content for tracking"""
    return hashlib.md5(content.encode()).hexdigest()[:8]


def generate_content(prompt, provider='claude'):
    if provider == 'openai':
        if not openai_api_key:
            return "OpenAI API key not set."
        client = openai.OpenAI(api_key=openai_api_key)
        try:
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=2000
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            return str(e)
    elif provider == 'claude':
        if not claude_api_key:
            return "Claude API key not set."
        client = anthropic.Anthropic(api_key=claude_api_key)
        try:
            response = client.messages.create(
                model="claude-3-haiku-20240307",
                max_tokens=2000,
                messages=[{"role": "user", "content": prompt}]
            )
            return response.content[0].text.strip()
        except Exception as e:
            return str(e)
    else:
        return "Invalid provider."

@app.route('/generate', methods=['POST'])
def generate():
    data = request.json
    url = data.get('url')
    requirements = data.get('requirements')
    brand_guidelines = data.get('brand_guidelines')
    content_direction = data.get('content_direction', '')
    preapproved_content = data.get('preapproved_content', '')
    page_type = data.get('page_type')  # e.g., 'service_area'
    provider = data.get('provider', 'claude')
    locations = data.get('locations', [])
    keywords_raw = data.get('keywords', '') or ''
    keyword_list = [kw.strip() for kw in keywords_raw.split(',') if kw.strip()]
    primary_keyword = keyword_list[0] if keyword_list else ''
    secondary_keywords = keyword_list[1:] if len(keyword_list) > 1 else []
    max_retries = 3

    site_data = scrape_website(url)
    existing_pages = site_data.get('links', [])
    existing_page_texts = site_data.get('page_texts', {})

    if page_type == 'service_area':
        locations = [loc for loc in locations if loc]
        if not locations:
            locations = ['Service Area']
    else:
        locations = [page_type.replace('_', ' ').title() if page_type else 'Landing Page']

    contents = {}

    for location in locations:
        retry_count = 0
        while retry_count < max_retries:
            previously_generated = "\n---\n".join([
                f"{loc}: {cont[:200]}..." for loc, cont in contents.items()
            ]) if contents else "None"

            existing_page_summary = "\n".join([
                f"{path}: {text[:200]}..." for path, text in existing_page_texts.items()
            ]) or 'No existing page text available.'

            direction_note = f"\n\nPage direction: {content_direction}" if content_direction else ''
            preapproved_note = f"\n\nPre-approved content to include verbatim: {preapproved_content}" if preapproved_content else ''

            prompt = f"""You are generating landing page content for a new landing page. Use the website context and provided inputs, but keep the content grounded and natural. Avoid generic marketing clichés, exaggerated claims, or overly dramatic language.

Website URL: {url}
Existing site page samples:
{existing_page_summary}

Page intent: Generate content for a {page_type} page for {location}.
Design requirements: {requirements}
Primary keyword: {primary_keyword}
Secondary keywords: {', '.join(secondary_keywords) if secondary_keywords else 'None'}
Brand guidelines: {brand_guidelines}
If Pre-approved content is provided, analyze its tone, voice, and style, and ensure the generated content matches that approved tone.{direction_note}{preapproved_note}

Requirements:
- Rely on actual website context and the provided inputs.
- If the page does not exist yet, do not invent details. Keep the content factual, helpful, and plausible.
- Use the primary keyword as the main focus of the content.
- Use secondary keywords naturally where relevant, without forcing them.
- Avoid cannibalization with existing website pages.
- Avoid duplicate content across the generated pages.
- Use the requested page direction or blurb to shape the structure.
- Keep the tone natural, conversational, and easy to read.
- Bold any exact keyword phrases from the Keywords field using **keyword**.
- Provide 8-9 FAQs with each question and answer on separate lines.
- Use clear headings and spacing for readability.

Formatting:
- Begin with a title line using `#` and a short intro paragraph.
- Use `##` for main section headings.
- Separate sections with blank lines.
- Write one concise paragraph under each heading.
- Format FAQs like:
  Q: ...
  A: ...
  Q: ...
  A: ...
- Do not output escaped newline characters like `\n`.

Write the landing page content in a calm, human tone and include a FAQ section at the end."""

            content = generate_content(prompt, provider)
            content = bold_keywords(content, keywords_raw)

            is_dup_existing, existing_path, existing_similarity = is_duplicate_content(content, existing_page_texts)
            is_dup_generated, dup_with_generated, generated_similarity = is_duplicate_content(content, contents)

            if (is_dup_existing or is_dup_generated) and retry_count < max_retries - 1:
                retry_count += 1
                continue

            contents[location] = content
            break

    return jsonify({"contents": contents})

if __name__ == '__main__':
    app.run(debug=True)