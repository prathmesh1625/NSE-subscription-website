const express =
    require(
        "express"
    );

const router =
    express.Router();

const authMiddleware =
    require(
        "../middlewares/authMiddleware"
    );

const userController =
    require(
        "../controllers/userController"
    );

router.delete(

    "/account",

    authMiddleware,

    userController
        .deleteAccount

);

module.exports =
    router;
