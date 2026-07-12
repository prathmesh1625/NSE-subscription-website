const express = require("express");
const adminAuthMiddleware = require("./adminAuthMiddleware");
const adminController = require("./adminController");

const router = express.Router();

// Every route here requires the shared central-dashboard API key.
router.use(adminAuthMiddleware);

router.get("/meta", adminController.meta);
router.get("/stats", adminController.stats);
router.get("/stats/:key/detail", adminController.statDetail);
router.get("/users", adminController.listUsers);
router.get("/users/:id", adminController.getUser);
router.post("/users/:id/actions/:actionKey", adminController.runAction);
router.get("/options/:key", adminController.getOptions);

module.exports = router;
