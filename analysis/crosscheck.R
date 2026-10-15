# Third, fully independent implementation: R fixest on the exported estimation panels.
# Fails (non-zero exit) if any headline coefficient or CR1 standard error disagrees with analysis/results.
suppressPackageStartupMessages({
  library(fixest)
  library(jsonlite)
})

panels <- "target/analysis_panels"
results <- "analysis/results"
delist <- fromJSON(file.path(results, "delist.json"))
pricing <- fromJSON(file.path(results, "pricing.json"))
cr1 <- ssc(adj = FALSE, cluster.adj = TRUE)  # matches analysis/fe.py: c = G / (G - 1)

checks <- data.frame(check = character(), primary = numeric(), fixest = numeric(), stringsAsFactors = FALSE)
add <- function(name, primary, value) {
  checks[nrow(checks) + 1, ] <<- list(name, primary, value)
}

# Q1: indexed GP, store + week FE, treated x post, clustered by store.
d <- read.csv(file.path(panels, "delist_panel.csv"))
switch_index <- min(d$week_index[d$week_key == "FY2025-W27"])
base <- aggregate(gp ~ store_id, data = d[d$week_index < switch_index, ], FUN = mean)
names(base)[2] <- "base_gp"
d <- merge(d, base, by = "store_id")
d$y <- d$gp / d$base_gp
d$treat <- as.numeric(d$store_id %in% delist$treated_stores & d$week_index >= switch_index)
m <- feols(y ~ treat | store_id + week_key, data = d, cluster = ~store_id, ssc = cr1)
add("delist_gp_beta", delist$gp$beta, unname(coef(m)["treat"]))
add("delist_gp_se_cr1", delist$gp$se_cr1, unname(se(m)["treat"]))

# Q3: both designs, both events; log units on own and cross dose, clustered by store.
designs <- list(preregistered = "fe_a + fe_b", zone_dose = "fe_a + fe_b + fe_c")
for (design in names(designs)) {
  for (event in c("golden_ridge_kettle", "bramble_select_tortilla")) {
    p <- read.csv(file.path(panels, paste0(event, "_", design, ".csv")))
    f <- as.formula(paste("log_units ~ x_own + x_cross |", designs[[design]]))
    m <- feols(f, data = p, cluster = ~store_id, ssc = cr1)
    for (x in c("x_own", "x_cross")) {
      primary <- pricing[[design]][[event]][[x]]
      add(paste(design, event, x, "beta", sep = "_"), primary$elasticity, unname(coef(m)[x]))
      add(paste(design, event, x, "se", sep = "_"), primary$se_store_cr1, unname(se(m)[x]))
    }
  }
}

# Q2: cannibalisation slopes of the promotion baseline model (clean weeks), three FEs, clustered by store.
promotions <- fromJSON(file.path(results, "promotions.json"))
p <- read.csv(file.path(panels, "promotions_clean.csv"))
xs <- grep("^cann_", names(p), value = TRUE)
m <- feols(as.formula(paste("y ~", paste(xs, collapse = " + "), "| fe_a + fe_b + fe_c")),
           data = p, cluster = ~cluster_id, ssc = cr1)
for (s in names(promotions$cannibalisation)) {
  x <- paste0("cann_", gsub(" ", "_", tolower(s)))
  add(paste("promotions", x, "beta", sep = "_"), promotions$cannibalisation[[s]]$per_promoted_sister,
      unname(coef(m)[x]))
  add(paste("promotions", x, "se", sep = "_"), promotions$cannibalisation[[s]]$se_store_cr1, unname(se(m)[x]))
}

# Primary results are stored at 6 significant figures.
checks$abs_diff <- abs(checks$primary - checks$fixest)
checks$pass <- checks$abs_diff <= pmax(1e-5, 5e-6 * abs(checks$fixest))
print(checks, digits = 8)
write_json(list(status = ifelse(all(checks$pass), "pass", "fail"),
                fixest_version = as.character(packageVersion("fixest")), checks = checks),
           file.path("target", "crosscheck_fixest.json"), auto_unbox = TRUE, digits = 10, pretty = TRUE)
if (!all(checks$pass)) {
  stop(paste("fixest disagrees on:", paste(checks$check[!checks$pass], collapse = ", ")))
}
