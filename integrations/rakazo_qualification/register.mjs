import { register } from "node:module";

register("./pinned_loader.mjs", import.meta.url);
