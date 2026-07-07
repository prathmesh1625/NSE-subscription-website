const fetchBseAnnouncements =
    require("./fetchBseAnnouncements");

(async () => {

    const data =
        await fetchBseAnnouncements(
            "500325",
            "RELIANCE"
        );

    console.log(
        JSON.stringify(
            data,
            null,
            2
        )
    );

})();