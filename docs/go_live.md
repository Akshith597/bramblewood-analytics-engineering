# Publish the project with GitHub and GitHub Pages

Use two public links in applications: the GitHub repository for code and the GitHub Pages site for the interactive dbt documentation, including lineage and compiled SQL.

## 1. Create the repository

On GitHub, create a **public** repository named `bramblewood-analytics-engineering`. Leave the repository empty: do not initialize a README, license or gitignore there, because this project already contains its files.

Unzip the project and open a terminal in the directory containing `dbt_project.yml`, `README.md` and `.github`. Replace `YOUR_USERNAME` in the command below with your actual GitHub username.

```text
git init
git branch -M main
git add .
git commit -m "Add Bramblewood analytics engineering portfolio"
git remote add origin https://github.com/YOUR_USERNAME/bramblewood-analytics-engineering.git
git push -u origin main
```

GitHub authentication may prompt you to sign in. Generated `warehouse/`, `target/`, `logs/` and `public_site/` files are ignored; source code, data and evidence are committed.

## 2. Enable GitHub Pages

In your repository, open **Settings → Pages**. Under **Build and deployment**, set **Source → GitHub Actions**. No additional workflow template is needed: `.github/workflows/pages.yml` is included.

See [GitHub's publishing-source instructions](https://docs.github.com/en/pages/getting-started-with-github-pages/configuring-a-publishing-source-for-your-github-pages-site).

## 3. Run the deployment

Open **Actions → Publish dbt documentation → Run workflow** and select `main`. If the workflow already ran before Pages was enabled and failed, rerun it after completing the setting above.

The workflow installs the dependencies, rebuilds the warehouse, runs all tests and independent reconciliation, generates the docs, and deploys the static documentation only after those commands pass. Future pushes to `main` repeat that process.

The **Deploy documentation** step and **Settings → Pages** show the actual site URL. With the repository name above and no custom domain, the expected address is:

```text
https://YOUR_USERNAME.github.io/bramblewood-analytics-engineering/
```

The site is the interactive dbt catalog. It supports exploring models, lineage and SQL; the warehouse itself remains a reproducible build artifact. See [GitHub's custom workflow documentation](https://docs.github.com/en/pages/getting-started-with-github-pages/using-custom-workflows-with-github-pages).

## 4. Make both links easy to find

Add the live Pages URL to the repository's **About → Website** field and to the README. Pin the repository on your GitHub profile. Add both repository and live documentation links to your resume project entry and portfolio.

Open the published URL in a signed-out browser and check that the models load and the lineage view works before sharing it with recruiters.

## If deployment fails

- **Pages is not configured:** Check that the publishing source is GitHub Actions, then rerun the workflow.
- **A test or reconciliation failed:** Open the failed step's logs and fix the source/model issue before rerunning. Deployment deliberately stops when the build fails.
- **Deployment permission error:** Check that Actions is enabled and your repository permits the included workflow. The deployment job requests `pages: write` and `id-token: write` as required by GitHub.
- **Wrong branch:** This workflow publishes `main`. Rename your default branch to `main`, or update the push filter and deployment condition together.

This project's repository is [Akshith597/bramblewood-analytics-engineering](https://github.com/Akshith597/bramblewood-analytics-engineering). Its documentation URL is [the interactive dbt catalog](https://akshith597.github.io/bramblewood-analytics-engineering/). Check the repository's Actions tab for the actual latest build and deployment results. The steps above also apply to publishing a fork under your own account.
