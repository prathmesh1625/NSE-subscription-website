const { client } = require("./httpClient");
const limiter = require("./requestLimiter");
const retry = require("./retry");

const FEED_URL =
    "https://api.bseindia.com/BseIndiaAPI/api/AnnSubCategoryGetData/w";

const ATTACHMENT_BASE =
    "https://www.bseindia.com/xml-data/corpfiling/AttachLive/";

const PAGE_SIZE = 50;

/**
 * Strip BSE's "<Company Name> - <scrip code> - " prefix from a subject line.
 *
 * BSE prefixes every NEWSSUB with the company name and scrip code; NSE's
 * equivalent field carries the bare subject. Removing it makes BSE titles read
 * like NSE ones in the WhatsApp caption, and — more importantly — lets the
 * bot's cross-exchange dedup recognise the same filing from both feeds.
 */
function cleanTitle(row) {

    const subject = String(row.NEWSSUB || "").trim();
    const code = String(row.SCRIP_CD || "").trim();

    if (subject && code) {
        const marker = ` - ${code} - `;
        const at = subject.indexOf(marker);

        if (at !== -1) {
            const rest = subject.slice(at + marker.length).trim();
            if (rest) {
                return rest;
            }
        }
    }

    return subject || String(row.HEADLINE || "").trim();
}

function normalise(row) {

    const attachment = String(row.ATTACHMENTNAME || "").trim();

    return {
        newsId: row.NEWSID || null,

        // Numeric in the JSON payload — the subscribed-symbol map is keyed on
        // strings, so pin the type here rather than at every call site.
        scripCd: String(row.SCRIP_CD || "").trim(),

        companyName: String(row.SLONGNAME || "").trim(),

        title: cleanTitle(row),

        headline: String(row.HEADLINE || "").trim(),

        category: String(row.CATEGORYNAME || "").trim(),

        subCategory: String(row.SUBCATNAME || "").trim(),

        // NEWS_DT is when the company filed; DissemDT is when BSE published it.
        // The filing time is what subscribers care about, and it is what the
        // NSE rows in the same table hold.
        announcedAt: row.NEWS_DT || row.DT_TM || row.News_submission_dt || null,

        disseminatedAt: row.DissemDT || row.DT_TM || null,

        attachment,

        pdfUrl: attachment ? `${ATTACHMENT_BASE}${attachment}` : null
    };

}

/**
 * Fetch ONE page of BSE's global corporate-announcements feed (newest first).
 *
 * Two undocumented constraints, both of which make the API answer with a bare
 * `{}` instead of an error when violated:
 *   - `pageno` is mandatory.
 *   - with `strScrip` empty (all companies), `strPrevDate` and `strToDate` must
 *     be the SAME day. A multi-day range returns nothing at all.
 *
 * Returns { rows, total } — `total` is BSE's own row count for the day, used to
 * decide whether another page exists. Returns an empty page on failure so one
 * bad request can never blank out a cycle.
 */
async function fetchBsePage(day, pageNo) {

    return limiter.execute(() =>
        retry(async () => {

            const response = await client.get(FEED_URL, {
                params: {
                    pageno: pageNo,
                    strCat: "-1",
                    strPrevDate: day,
                    strToDate: day,
                    strScrip: "",
                    strSearch: "P",
                    strType: "C",
                    subcategory: "-1"
                }
            });

            const data = response.data;

            if (!data || !Array.isArray(data.Table)) {
                return { rows: [], total: 0 };
            }

            return {
                rows: data.Table.map(normalise),
                total: Number(
                    (data.Table1 && data.Table1[0] && data.Table1[0].ROWCNT) || 0
                )
            };

        }, 2, 1200)
    ).catch(err => {

        console.log(
            `BSE feed ${day} page ${pageNo} failed: ${err.message}`
        );

        return { rows: [], total: 0 };

    });

}

module.exports = {
    fetchBsePage,
    ATTACHMENT_BASE,
    PAGE_SIZE
};
