# Requires: pip install mistune Pygments
import mistune
from pygments import highlight
from pygments.lexers import get_lexer_by_name, guess_lexer
from pygments.formatters import HtmlFormatter
from pygments.util import ClassNotFound
import html

class HighlightRenderer(mistune.HTMLRenderer):
    def block_code(self, code, info=None):
        lexer = None
        if info:
            try:
                lexer = get_lexer_by_name(info, stripall=True)
            except ClassNotFound:
                try:
                    lexer = guess_lexer(code) # Corrected
                except ClassNotFound:
                    lexer = None
        else: 
            try:
                lexer = guess_lexer(code) # Corrected
            except ClassNotFound:
                lexer = None
        
        if lexer:
            formatter = HtmlFormatter(cssclass="highlight", linenos=False)
            return highlight(code, lexer, formatter)
        
        return '<pre class="highlight"><code>' + html.escape(code) + '</code></pre>'

markdown_parser = mistune.create_markdown(renderer=HighlightRenderer(escape=False))

def render_markdown(text: str) -> str:
    """Converts a markdown string to styled HTML with syntax highlighting."""
    return markdown_parser(text)

if __name__ == '__main__':
    test_markdown = """
# Heading 1
This is some **bold** and *italic* text.
`inline code` here.

And a link: [Google](https://www.google.com)

An image: ![alt text](https://path.to/image.png)

```python
def hello_world():
    # This is a comment
    print("Hello, syntax highlighting!")
    return {"key": "value"}
```

```javascript
function greet(name) {
    // JS comment
    console.log(`Hello, ${name}!`);
    return true;
}
```

```
No language specified (should try to guess or fallback):
This should be plain preformatted text.
<script>alert('XSS if not escaped')</script>
```

```html
<!DOCTYPE html>
<html>
<head>
    <title>Test HTML</title>
</head>
<body>
    <h1>Hello HTML</h1>
    <p>This is a paragraph.</p>
</body>
</html>
```

```foobar_language_unknown
# This language is not known by Pygments
# It should fallback to plain preformatted text
my_var = 123 * 456;
```
    """
    html_output = render_markdown(test_markdown)
    print("--- HTML Output ---")
    print(html_output)
    
    print("\n--- Test with only unknown language ---")
    unknown_lang_md = "```foobar\nthis is some code\n```"
    print(render_markdown(unknown_lang_md))

    print("\n--- Test with no language ---")
    no_lang_md = "```\nplain code block here\n```"
    print(render_markdown(no_lang_md))

    print("\n--- Test with just text ---")
    just_text_md = "Just plain text with an ampersand & and a <tag>."
    print(render_markdown(just_text_md))

    print("\n--- Test with inline code ---")
    inline_code_md = "This is `inline_code_example = true;` and then more text."
    print(render_markdown(inline_code_md))

    # Example of how Pygments HtmlFormatter wraps code:
    # Default (no cssclass on HtmlFormatter): <div><pre>...</pre></div>
    # With cssclass="highlight": <div class="highlight"><pre>...</pre></div>
    # The <pre> will contain <span> elements with classes like 'k' (keyword), 's' (string), etc.
    # These are styled by the Pygments CSS.
