# 🔍 WhatsApp Template Error Debugging Guide

## 🎯 Purpose
This guide helps debug **Meta WhatsApp API Error 100 (Invalid Parameter)** errors when sending template messages.

---

## 📊 What You'll See Now

### **Enhanced Debug Logs:**

When a template is sent, you'll see **complete parameter details**:

```
================================================================================
[WA TEMPLATE DEBUG] name='nse_bot' lang='en' params=5
================================================================================

📋 Param 1 (27 chars):
--------------------------------------------------------------------------------
📢 *EquityAlerts NSE Bot*
--------------------------------------------------------------------------------
✅ No obvious formatting issues

📋 Param 2 (26 chars):
--------------------------------------------------------------------------------
RELIANCE INDUSTRIES
--------------------------------------------------------------------------------
✅ No obvious formatting issues

📋 Param 3 (59 chars):
--------------------------------------------------------------------------------
Financial Results - Board Meeting Intimation
--------------------------------------------------------------------------------
✅ No obvious formatting issues

📋 Param 4 (400 chars):
--------------------------------------------------------------------------------
Reliance Industries announces Board Meeting on Aug 25 2026 to consider quarterly results...
... +210 more chars
--------------------------------------------------------------------------------
⚠️  POTENTIAL ISSUES:
   ❌ Contains 5 newlines
   ❌ Contains runs of 4+ spaces

📋 Param 5 (33 chars):
--------------------------------------------------------------------------------
https://example.com/filing.pdf
--------------------------------------------------------------------------------
✅ No obvious formatting issues

================================================================================
```

---

## 🐛 Common Issues & Fixes

### **1. Newlines in Parameters**
**Problem:** Template params contain `\n` characters  
**Fix:** Already handled by `_sanitize_template_param()` - converts to spaces

### **2. Control Characters**
**Problem:** Hidden characters like tabs, carriage returns  
**Fix:** Already stripped by sanitization

### **3. Markdown Formatting**
**Problem:** `*bold*`, `_italic_`, `` `code` `` in parameters  
**Fix:** Already stripped by sanitization

### **4. Parameter Too Long**
**Problem:** Individual param exceeds Meta's limits  
**Fix:** Truncated to 900 chars per param (or fitted to 1024 total)

### **5. Template Mismatch**
**Problem:** Template expects 5 params, you send 3  
**Fix:** Check `TEMPLATE_BODY_PARAM_COUNT` in config

---

## 🔧 What the Sanitization Does

The `_sanitize_template_param()` function:

1. ✅ Removes all control characters (newlines, tabs, etc.)
2. ✅ Collapses multiple spaces into single spaces
3. ✅ Strips markdown formatting (`*`, `_`, `` ` ``, `~`)
4. ✅ Removes zero-width characters
5. ✅ Truncates to 900 chars max
6. ✅ Fits entire rendered template under 1024 chars

---

## 🎯 How to Debug Error 100

### **Step 1: Check the Debug Logs**
Look for the detailed parameter dump in your logs.

### **Step 2: Identify the Problem Parameter**
The logs show:
- Exact content of each parameter
- Character count
- Any problematic formatting

### **Step 3: Check Your Template**
In Meta Business Manager:
1. Go to **WhatsApp Manager → Message Templates**
2. Find your template (`nse_bot`)
3. Count the `{{1}}`, `{{2}}`, etc. variables
4. Ensure `TEMPLATE_BODY_PARAM_COUNT` matches

### **Step 4: Verify Template Approval**
- Template must be **APPROVED** by Meta
- Template language must match `TEMPLATE_LANG` in config

---

## 📝 Template Configuration

### **Required Environment Variables:**

```env
# Template name (must be approved in Meta Manager)
TEMPLATE_NAME=nse_bot

# Template language code
TEMPLATE_LANG=en

# Number of {{n}} variables in template BODY (not header)
TEMPLATE_BODY_PARAM_COUNT=5

# Does template have a DOCUMENT header?
TEMPLATE_HAS_DOCUMENT_HEADER=true
```

---

## 🚨 Common Meta Error Codes

| Code   | Meaning | Solution |
|--------|---------|----------|
| 100    | Invalid Parameter | Parameter contains invalid formatting or template mismatch |
| 131026 | Recipient Not Verified | Add number to test recipients in Meta Manager |
| 131047 | 24-Hour Window Closed | Already handled - falls back to template automatically |
| 131053 | Service Unavailable | Retry later |
| 130472 | Invalid Number | Number not on WhatsApp |

---

## 🎯 Next Steps After Seeing Error 100

1. **Check the debug logs** - find which parameter has issues
2. **Verify template config** - ensure param count matches
3. **Check template approval** - must be APPROVED in Meta Manager
4. **Verify sanitization** - logs show what's AFTER sanitization
5. **Check template structure** - header type (TEXT vs DOCUMENT)

---

## 📚 Related Files

- **bot/whatsapp.py** - Template sending logic
- **bot/config.py** - Template configuration
- **bot/db_watcher.py** - Constructs template parameters

---

## 💡 Pro Tips

1. **Always check the debug logs first** - they show exactly what Meta is receiving
2. **Template changes require re-approval** - changes in Meta Manager need approval before they work
3. **Test with simple text first** - start with plain text params to isolate issues
4. **Verify param count** - most common issue is mismatch between code and template

---

**Need more help?** Check the full response in Meta's error message - the `fbtrace_id` can be used for Meta support tickets.
