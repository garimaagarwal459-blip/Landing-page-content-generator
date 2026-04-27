# Content Generation Tool

This tool generates content for new website pages that don't already exist, such as service area pages or landing pages.

## Setup

1. Install dependencies: `pip install -r requirements.txt`
2. Set your API keys as environment variables:
   - `export OPENAI_API_KEY='your-openai-key-here'` (optional)
   - `export CLAUDE_API_KEY='your-claude-key-here'`
3. Run the app: `./run.sh`
4. Open http://127.0.0.1:5000/ in your browser.

## Usage

- Enter the website URL.
- Provide design requirements and brand guidelines.
- Select page type (service area or landing).
- For service areas, enter locations separated by commas.
- Click Generate Content to get AI-generated content.

## Features

- Scrapes existing pages to avoid duplication.
- Uses OpenAI to generate SEO-friendly content.
- Incorporates brand guidelines.
- Supports multiple page types.

Note: You need an OpenAI API key for content generation.