user request: {{user_request}}

Based on user requirements, please determine whether to retain all of the following clips:
{{clip_captions}}

Output format as follows:
Note: Only output the content in the following required formats. It is strictly prohibited to output any other content
```json
{
  "results": [
    {"clip_id": "clip_0001", "keep": true}
    {"clip_id": "clip_0002", "keep": false}
  ]
}
```