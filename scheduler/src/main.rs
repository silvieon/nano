use std::{
    collections::{HashMap, HashSet},
    io::{self, Read},
    sync::Arc,
    time::Duration,
};

use serde::{Deserialize, Serialize};
use tokio::{sync::Mutex, time::sleep};

#[derive(Debug, Deserialize, Serialize, Clone)]
struct RuntimePlan {
    version: u32,
    tasks: Vec<RuntimeTask>,
}

#[derive(Debug, Deserialize, Serialize, Clone)]
struct RuntimeTask {
    id: String,
    service: String,
    operation: String,
    #[serde(default)]
    arguments: serde_json::Value,
    #[serde(default)]
    depends_on: Vec<String>,
    #[serde(default = "default_timeout")]
    timeout_ms: u64,
    #[serde(default)]
    retry_limit: u32,
}

fn default_timeout() -> u64 {
    30_000
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum State {
    Pending,
    Ready,
    Running,
    Succeeded,
    Failed,
}

#[derive(Debug, Clone)]
struct RuntimeState {
    states: Arc<Mutex<HashMap<String, State>>>,
}

#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    let mut input = String::new();
    io::stdin().read_to_string(&mut input)?;

    if input.trim().is_empty() {
        eprintln!("usage: cat runtime-plan.json | nano-scheduler");
        std::process::exit(2);
    }

    let plan: RuntimePlan = serde_json::from_str(&input)?;
    validate_plan(&plan)?;

    println!("=== nano scheduler ===");
    println!("plan version: {}", plan.version);
    println!("tasks: {}", plan.tasks.len());
    println!();

    let state = RuntimeState {
        states: Arc::new(Mutex::new(
            plan.tasks
                .iter()
                .map(|t| (t.id.clone(), State::Pending))
                .collect(),
        )),
    };

    let tasks = Arc::new(plan.tasks);
    let mut handles = Vec::new();

    loop {
        let snapshot = state.states.lock().await.clone();

        if snapshot
            .values()
            .all(|s| matches!(s, State::Succeeded))
        {
            break;
        }

        if snapshot.values().any(|s| matches!(s, State::Failed)) {
            println!("scheduler: stopping because a task failed");

            for handle in handles {
                handle.await?;
            }

            return Err("scheduler: task failure".into());
        }

        // Promote dependency-satisfied tasks from PENDING to READY.
        for task in tasks.iter() {
            if snapshot.get(&task.id) != Some(&State::Pending) {
                continue;
            }

            let deps_ready = task
                .depends_on
                .iter()
                .all(|dep| snapshot.get(dep) == Some(&State::Succeeded));

            if deps_ready {
                state
                    .states
                    .lock()
                    .await
                    .insert(task.id.clone(), State::Ready);

                println!("READY    {}", task.id);
            }
        }

        let ready_snapshot = state.states.lock().await.clone();
        let mut launched = false;

        for task in tasks.iter() {
            if ready_snapshot.get(&task.id) != Some(&State::Ready) {
                continue;
            }

            launched = true;

            state
                .states
                .lock()
                .await
                .insert(task.id.clone(), State::Running);

            let task = task.clone();
            let state_clone = state.clone();

            handles.push(tokio::spawn(async move {
                println!(
                    "START    {}  [{}:{}]",
                    task.id, task.service, task.operation
                );

                if !task.depends_on.is_empty() {
                    println!("         depends_on: {:?}", task.depends_on);
                }

                if task.arguments != serde_json::Value::Null
                    && task.arguments != serde_json::json!({})
                {
                    println!("         args: {}", task.arguments);
                }

                let outcomes = simulated_outcomes(&task.arguments);
                let mut attempt = 0usize;

                loop {
                    attempt += 1;

                    println!("ATTEMPT  {}  #{}", task.id, attempt);

                    // Simulation only. The call plane will replace this
                    // sleep later.
                    sleep(Duration::from_millis(250)).await;

                    let outcome = outcomes
                        .get(attempt - 1)
                        .map(String::as_str)
                        .unwrap_or("success");

                    if outcome == "success" {
                        state_clone
                            .states
                            .lock()
                            .await
                            .insert(task.id.clone(), State::Succeeded);

                        println!("DONE     {}", task.id);
                        break;
                    }

                    let failure_class = simulated_failure_class(&task.arguments);

                    println!(
                        "FAIL     {}  attempt={} class={}",
                        task.id, attempt, failure_class
                    );

                    let retries_used = (attempt - 1) as u32;

                    if failure_class == "transient"
                        && retries_used < task.retry_limit
                    {
                        println!(
                            "RETRY    {}  next_attempt={} remaining={}",
                            task.id,
                            attempt + 1,
                            task.retry_limit - retries_used
                        );

                        continue;
                    }

                    state_clone
                        .states
                        .lock()
                        .await
                        .insert(task.id.clone(), State::Failed);

                    println!("FAILED   {}", task.id);
                    break;
                }
            }));
        }

        if !launched {
            let snapshot = state.states.lock().await.clone();

            let running = snapshot
                .values()
                .any(|s| matches!(s, State::Running));

            let ready = snapshot
                .values()
                .any(|s| matches!(s, State::Ready));

            let pending: Vec<_> = snapshot
                .iter()
                .filter(|(_, s)| **s == State::Pending)
                .map(|(id, _)| id.clone())
                .collect();

            if !pending.is_empty() && !running && !ready {
                return Err(
                    format!(
                        "scheduler deadlock; pending tasks: {:?}",
                        pending
                    )
                    .into(),
                );
            }
        }

        sleep(Duration::from_millis(25)).await;
    }

    for handle in handles {
        handle.await?;
    }

    println!();
    println!("scheduler: plan complete");

    Ok(())
}

fn simulated_outcomes(arguments: &serde_json::Value) -> Vec<String> {
    let Some(simulate) = arguments.get("simulate") else {
        return vec!["success".to_string()];
    };

    if let Some(outcomes) = simulate
        .get("outcomes")
        .and_then(|v| v.as_array())
    {
        return outcomes
            .iter()
            .filter_map(|v| v.as_str().map(str::to_string))
            .collect();
    }

    if let Some(outcome) = simulate
        .get("outcome")
        .and_then(|v| v.as_str())
    {
        return vec![outcome.to_string()];
    }

    vec!["success".to_string()]
}

fn simulated_failure_class(arguments: &serde_json::Value) -> &str {
    arguments
        .get("simulate")
        .and_then(|v| v.get("failure_class"))
        .and_then(|v| v.as_str())
        .unwrap_or("transient")
}

fn validate_plan(
    plan: &RuntimePlan,
) -> Result<(), Box<dyn std::error::Error>> {
    let ids: HashSet<&str> =
        plan.tasks.iter().map(|t| t.id.as_str()).collect();

    if ids.len() != plan.tasks.len() {
        return Err("duplicate task IDs".into());
    }

    for task in &plan.tasks {
        for dep in &task.depends_on {
            if !ids.contains(dep.as_str()) {
                return Err(
                    format!(
                        "unknown dependency: {} -> {}",
                        task.id, dep
                    )
                    .into(),
                );
            }

            if dep == &task.id {
                return Err(
                    format!("self dependency: {}", task.id).into()
                );
            }
        }
    }

    Ok(())
}