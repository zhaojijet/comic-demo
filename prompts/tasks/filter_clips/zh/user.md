用户要求: {{user_request}}
请根据用户要求，判断下面所有 clips 是否保留
{{clip_captions}}
输出格式如下：
注意:只输出以下要求格式的内容，严格禁止输出其他内容
```json
{
  "results": [
    {"clip_id": "clip_0001", "keep": true},
    {"clip_id": "clip_0002", "keep": false}
  ]
}
```