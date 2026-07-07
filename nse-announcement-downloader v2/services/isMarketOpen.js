function isMarketOpen() {

    const now =
        new Date();

    const hour =
        now.getHours();

    const minute =
        now.getMinutes();

    const total =

        hour * 60
        +
        minute;

    const open =
        8 * 60;

    const close =
        18 * 60;

    return (

        total >= open
        &&
        total <= close

    );

}

module.exports =
    isMarketOpen;