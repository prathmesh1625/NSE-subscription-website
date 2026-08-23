# 🚀 QUICK START - Fix Your Bot NOW

## ⚡ **TWO COMMANDS TO RUN:**

### **1. Clean Up Old Filings (Run Once)**
```bash
psql -U your_user -d your_database -f CLEANUP_OLD_FILINGS_RUN_NOW.sql
```

**This removes the 46-hour old backlog from your logs.**

---

### **2. Redeploy Bot**
```bash
# If using Coolify - it auto-deploys (already done via git push)
# If manual deployment:
docker-compose restart bot
# OR
pm2 restart bot
```

---

## 📊 **WHAT HAPPENS NEXT:**

When the next NSE announcement arrives, you'll see:

```
================================================================================
[WA TEMPLATE DEBUG] name='nse_bot' lang='en' params=5
================================================================================

📋 Param 1 (27 chars):
--------------------------------------------------------------------------------
📢 *EquityAlerts NSE Bot*
--------------------------------------------------------------------------------
✅ No obvious formatting issues

📋 Param 4 (400 chars):
--------------------------------------------------------------------------------
Reliance Industries announces Board Meeting...
--------------------------------------------------------------------------------
⚠️  POTENTIAL ISSUES:
   ❌ Contains 3 newlines          <-- THIS IS YOUR PROBLEM
   ❌ Contains runs of 4+ spaces
```

**This shows EXACTLY what Meta is rejecting!**

---

## 🎯 **WHAT WAS FIXED:**

1. ✅ **Ultra-detailed template debugging** - see exact parameter content
2. ✅ **Character issue detection** - identifies newlines, tabs, control chars
3. ✅ **Database cleanup script** - removes 46-hour old backlog
4. ✅ **Comprehensive docs** - guides for every issue

---

## 📚 **DOCUMENTATION:**

- **URGENT_FIXES_APPLIED.md** - Complete deployment guide
- **TEMPLATE_ERROR_DEBUG_GUIDE.md** - How to fix Error 100
- **CLEANUP_OLD_FILINGS_RUN_NOW.sql** - Database cleanup script
- **LOGGING_GUIDE.md** - How to read all logs

---

## 🔧 **IF ISSUES PERSIST:**

### **Old Filings Still Showing?**
- Verify SQL script ran: `SELECT COUNT(*) FROM nse_announcements WHERE is_sent = FALSE AND created_at < NOW() - INTERVAL '6 hours';`
- Should return 0

### **Error 100 Still Happening?**
- Check the new debug logs (shows exact parameter content)
- Verify `TEMPLATE_BODY_PARAM_COUNT` in `bot/config.py`
- Check template approval in Meta Manager

---

**Changes pushed to GitHub! Coolify will auto-deploy.** 🎉

**Run the SQL cleanup and you're done!** ✅
