use std::path::Path;

use git2::Repository;
use std::fs::File;
use std::io::{BufReader, Read};

enum Command {
    Commit,
    Pull,
    Push,
    Reset,
    ForcePush,
    Squash,
    Abort,
    Rebase,
    Fetch,
    Sync,
}

impl Command {
    fn parse(cmd: &str) -> Self {
        match cmd {
            "commit" => Command::Commit,
            "pull" => Command::Pull,
            "push" => Command::Push,
            "reset" => Command::Reset,
            "force-push" => Command::ForcePush,
            "squash" => Command::Squash,
            "abort" => Command::Abort,
            "rebase" => Command::Rebase,
            "fetch" => Command::Fetch,
            "sync" => Command::Sync,
            _ => {
                println!("Unknown cmd: {}", cmd);
                std::process::exit(1);
            }
        }
    }
    fn icon(&self) -> &'static str {
        match self {
            Command::Commit => "💾 Commit",
            Command::Pull => "🔽 Pull",
            Command::Push => "🔼 Push",
            Command::Reset => "🪓 Reset",
            Command::ForcePush => "⏫ Force-Push",
            Command::Squash => "🧹 Squash",
            Command::Abort => "🛑 Abort",
            Command::Rebase => "🌳 Rebase",
            Command::Fetch => "🔃 Fetch",
            Command::Sync => "🔄️ Sync",
        }
    }

    fn start(&self) {
        println!("{} START", self.icon());
    }

    fn end(&self) {
        println!("{} END", self.icon());
    }

    fn run(&self) {
        self.start();
        self.run_cmd();
        self.end();
    }

    fn run_cmd(&self) {
        let repo = Repository::open("../small-team-git").expect("Failed to open repository");

        let my = repo.head().expect("Failed to get HEAD");
        let branch_name = my.shorthand().expect("Failed to get branch name");
        assert!(branch_name != "master" && branch_name != "main");
        println!("Current branch: {}", branch_name);

        // let origin = repo.find_remote("origin").expect("Failed to find remote");
        let master = repo
            .find_reference("refs/remotes/origin/master")
            .or_else(|_| repo.find_reference("refs/remotes/origin/main"))
            .expect("Failed to find master or main");
        println!(
            "Master: {}",
            master.shorthand().expect("Failed to get branch name")
        );

        match self {
            Command::Commit => self.commit(&repo, "update"),
            _ => {}
        }
    }
    fn is_dirty(&self, repo: &Repository) -> bool {
        let statuses = repo
            .statuses(None)
            .expect("Failed to get repository statuses");
        for entry in statuses.iter() {
            if entry.status() != git2::Status::CURRENT {
                return true;
            }
        }
        return false;
    }

    fn commit(&self, repo: &Repository, msg: &str) {
        if !self.is_dirty(repo) {
            return;
        }

        let mut index = repo.index().expect("Failed to get index");

        let head = repo.head().expect("Failed to get HEAD");
        let head_tree = head.peel_to_tree().expect("Failed to get HEAD tree");
        let index_tree = index
            .write_tree_to(repo)
            .expect("Failed to write index tree");
        let index_oid = repo
            .find_tree(index_tree)
            .expect("Failed to find index tree");

        if head_tree.id() == index_oid.id() {
            let mut status_options = git2::StatusOptions::new();
            status_options.include_untracked(true);
            status_options.recurse_untracked_dirs(true);

            let statuses = repo
                .statuses(Some(&mut status_options))
                .expect("Failed to get statuses");

            for entry in statuses.iter() {
                if let Some(path) = entry.path() {
                    index
                        .add_path(Path::new(path))
                        .expect(&format!("Failed to add path: {}", path));
                }
            }
        }

        index.write().expect("Failed to write index");

        let tree = index.write_tree().expect("Failed to write tree");
        let parent = repo.head().expect("Failed to get HEAD");
        let author =
            git2::Signature::now("Rongj", "rongj@outlook.com").expect("Failed to get author");
        let oid = repo
            .commit(

                None,
                &author,
                &author,
                msg,
                &repo.find_tree(tree).expect("Failed to find tree"),
                &[&parent.peel_to_commit().expect("Failed to peel to commit")],
            )
            .expect("Failed to commit");
        println!("Commit: {}", oid);
    }
}

fn main() {
    println!("Hello, world!");

    let arg = std::env::args().nth(1).expect("no cmd");
    match File::open("small-git.toml") {
        Ok(file) => {
            let mut reader = BufReader::new(file);
            let mut content = String::new();
            if let Err(e) = reader.read_to_string(&mut content) {
                eprintln!("读取文件内容失败: {}", e);
            } else {
                println!("{}", content);
            }
        }
        Err(e) => {
            eprintln!("无法打开文件 small-git.toml: {}", e);
        }
    }

    println!("cmd: {:?}", arg);
    let cmd = Command::parse(&arg);
    cmd.run();
}
