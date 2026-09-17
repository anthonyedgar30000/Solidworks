const CADGROUNDED = Object.freeze({
  handler: 'cadGroundedSchedulerTick',
  intervalMinutes: 5,
  statusBucketMinutes: 10,
  jobTtlMinutes: 20,
  maxFreshStatusMinutes: 20,
  expectedQueueRoot: 'C:\\ChatGPT\\Solidworks\\remote-queue',
  source: 'google_apps_script_readonly_scheduler_v1',
  propIncomingFolderId: 'CAD_QUEUE_INCOMING_FOLDER_ID',
  propResultsFolderId: 'CAD_QUEUE_RESULTS_FOLDER_ID',
  propBridgeReadyFileId: 'CAD_QUEUE_BRIDGE_READY_FILE_ID',
  propLastStatusJobId: 'CAD_LAST_STATUS_JOB_ID',
  propLastComponentsJobId: 'CAD_LAST_COMPONENTS_JOB_ID',
  propLastTickUtc: 'CAD_LAST_TICK_UTC'
});

function cadGroundedSchedulerDryRun() {
  const cfg = loadCadGroundedConfig_();
  const ready = readBridgeReady_(cfg.bridgeReadyFileId);
  assertReadOnlyBridge_(ready);

  const resultsFolder = DriveApp.getFolderById(cfg.resultsFolderId);
  const latestStatus = getLatestCompletedStatus_(resultsFolder);

  return {
    ok: true,
    write_authority: 'NONE',
    expected_queue_root: CADGROUNDED.expectedQueueRoot,
    bridge_queue_root: ready.queue_root,
    incoming_folder_id_present: !!cfg.incomingFolderId,
    results_folder_id_present: !!cfg.resultsFolderId,
    bridge_ready: true,
    latest_completed_status: latestStatus ? {
      job_id: latestStatus.job_id || null,
      finished_utc: latestStatus.finished_utc || null,
      document: extractDocumentFromStatusResult_(latestStatus)
    } : null
  };
}

function installCadGroundedScheduler() {
  const cfg = loadCadGroundedConfig_();
  const ready = readBridgeReady_(cfg.bridgeReadyFileId);
  assertReadOnlyBridge_(ready);

  ScriptApp.getProjectTriggers().forEach(trigger => {
    if (trigger.getHandlerFunction() === CADGROUNDED.handler) {
      ScriptApp.deleteTrigger(trigger);
    }
  });

  ScriptApp.newTrigger(CADGROUNDED.handler)
    .timeBased()
    .everyMinutes(CADGROUNDED.intervalMinutes)
    .create();

  return {
    installed: true,
    handler: CADGROUNDED.handler,
    every_minutes: CADGROUNDED.intervalMinutes,
    queue_root: ready.queue_root,
    write_authority: 'NONE'
  };
}

function uninstallCadGroundedScheduler() {
  let deleted = 0;
  ScriptApp.getProjectTriggers().forEach(trigger => {
    if (trigger.getHandlerFunction() === CADGROUNDED.handler) {
      ScriptApp.deleteTrigger(trigger);
      deleted++;
    }
  });
  return { deleted_triggers: deleted };
}

function cadGroundedSchedulerTick() {
  const lock = LockService.getScriptLock();
  if (!lock.tryLock(1000)) {
    return { skipped: 'another scheduler tick is active' };
  }

  try {
    const cfg = loadCadGroundedConfig_();
    const ready = readBridgeReady_(cfg.bridgeReadyFileId);
    assertReadOnlyBridge_(ready);

    const incomingFolder = DriveApp.getFolderById(cfg.incomingFolderId);
    const resultsFolder = DriveApp.getFolderById(cfg.resultsFolderId);
    const props = PropertiesService.getScriptProperties();
    const now = new Date();
    const actions = [];

    const statusBucket = floorDateToMinutes_(now, CADGROUNDED.statusBucketMinutes);
    const statusJobId = 'gdrive-status-' + formatUtcCompact_(statusBucket);
    const statusFileName = statusJobId + '.job.json';
    const statusResultName = statusJobId + '.result.json';

    if (
      props.getProperty(CADGROUNDED.propLastStatusJobId) !== statusJobId &&
      !fileExistsByName_(incomingFolder, statusFileName) &&
      !fileExistsByName_(resultsFolder, statusResultName)
    ) {
      const statusJob = {
        schema_version: 1,
        job_id: statusJobId,
        command_id: 'sw.status',
        write_authority: 'NONE',
        created_utc: now.toISOString(),
        expires_utc: addMinutes_(now, CADGROUNDED.jobTtlMinutes).toISOString(),
        source: CADGROUNDED.source,
        payload: {}
      };
      createJsonFile_(incomingFolder, statusFileName, statusJob);
      props.setProperty(CADGROUNDED.propLastStatusJobId, statusJobId);
      actions.push({ enqueued: 'sw.status', job_id: statusJobId });
    }

    const latestStatus = getLatestCompletedStatus_(resultsFolder);
    if (latestStatus) {
      const finished = new Date(latestStatus.finished_utc);
      const ageMinutes = (now.getTime() - finished.getTime()) / 60000;
      const document = extractDocumentFromStatusResult_(latestStatus);

      if (
        ageMinutes >= 0 &&
        ageMinutes <= CADGROUNDED.maxFreshStatusMinutes &&
        document &&
        document.title &&
        document.path
      ) {
        const componentBucket = floorDateToMinutes_(finished, CADGROUNDED.statusBucketMinutes);
        const componentsJobId = 'gdrive-components-' + formatUtcCompact_(componentBucket);
        const componentsFileName = componentsJobId + '.job.json';
        const componentsResultName = componentsJobId + '.result.json';

        if (
          props.getProperty(CADGROUNDED.propLastComponentsJobId) !== componentsJobId &&
          !fileExistsByName_(incomingFolder, componentsFileName) &&
          !fileExistsByName_(resultsFolder, componentsResultName)
        ) {
          const componentsJob = {
            schema_version: 1,
            job_id: componentsJobId,
            command_id: 'sw.query_components',
            write_authority: 'NONE',
            created_utc: now.toISOString(),
            expires_utc: addMinutes_(now, CADGROUNDED.jobTtlMinutes).toISOString(),
            source: CADGROUNDED.source,
            preconditions: {
              document_title_exact: document.title,
              document_path_exact: document.path
            },
            payload: {
              top_level_only: false
            }
          };
          createJsonFile_(incomingFolder, componentsFileName, componentsJob);
          props.setProperty(CADGROUNDED.propLastComponentsJobId, componentsJobId);
          actions.push({
            enqueued: 'sw.query_components',
            job_id: componentsJobId,
            document_title_exact: document.title
          });
        }
      }
    }

    props.setProperty(CADGROUNDED.propLastTickUtc, now.toISOString());

    return {
      ok: true,
      write_authority: 'NONE',
      bridge_ready: true,
      queue_root: ready.queue_root,
      actions: actions,
      tick_utc: now.toISOString()
    };
  } finally {
    lock.releaseLock();
  }
}

function loadCadGroundedConfig_() {
  const props = PropertiesService.getScriptProperties();
  const cfg = {
    incomingFolderId: props.getProperty(CADGROUNDED.propIncomingFolderId),
    resultsFolderId: props.getProperty(CADGROUNDED.propResultsFolderId),
    bridgeReadyFileId: props.getProperty(CADGROUNDED.propBridgeReadyFileId)
  };

  const propertyNames = {
    incomingFolderId: CADGROUNDED.propIncomingFolderId,
    resultsFolderId: CADGROUNDED.propResultsFolderId,
    bridgeReadyFileId: CADGROUNDED.propBridgeReadyFileId
  };

  Object.keys(cfg).forEach(key => {
    if (!cfg[key]) {
      throw new Error('Missing required Script Property: ' + propertyNames[key]);
    }
  });

  return cfg;
}

function readBridgeReady_(fileId) {
  const text = DriveApp.getFileById(fileId).getBlob().getDataAsString('UTF-8');
  return JSON.parse(text);
}

function assertReadOnlyBridge_(ready) {
  if (!ready || ready.schema_version !== 1) {
    throw new Error('Bridge-ready marker has unsupported schema_version.');
  }
  if (ready.type !== 'CADGrounded_RemoteQueue_Transport') {
    throw new Error('Bridge-ready marker type mismatch.');
  }
  if (ready.write_authority !== 'NONE') {
    throw new Error('Bridge-ready marker is not read-only.');
  }
  if (ready.queue_root !== CADGROUNDED.expectedQueueRoot) {
    throw new Error(
      'Bridge-ready queue_root mismatch. Expected=' +
      CADGROUNDED.expectedQueueRoot +
      ' Actual=' +
      String(ready.queue_root || '')
    );
  }
}

function getLatestCompletedStatus_(resultsFolder) {
  const files = resultsFolder.getFiles();
  let latest = null;
  let latestTime = -1;

  while (files.hasNext()) {
    const file = files.next();
    const name = file.getName();
    if (!name.endsWith('.result.json')) {
      continue;
    }

    let record;
    try {
      record = JSON.parse(file.getBlob().getDataAsString('UTF-8'));
    } catch (e) {
      continue;
    }

    if (!record || record.state !== 'completed') {
      continue;
    }

    const worker = record.worker_response || {};
    if (worker.command_id !== 'sw.status' || worker.ok !== true) {
      continue;
    }

    const finished = Date.parse(record.finished_utc || '');
    if (!Number.isFinite(finished)) {
      continue;
    }

    if (finished > latestTime) {
      latest = record;
      latestTime = finished;
    }
  }

  return latest;
}

function extractDocumentFromStatusResult_(record) {
  if (!record) return null;

  const worker = record.worker_response || {};
  if (worker.command_id === 'sw.status' && worker.ok === true && worker.data) {
    return worker.data.document || null;
  }

  const observed = record.status_observation || {};
  if (observed.command_id === 'sw.status' && observed.ok === true && observed.data) {
    return observed.data.document || null;
  }

  return null;
}

function createJsonFile_(folder, fileName, obj) {
  const json = JSON.stringify(obj, null, 2) + '\n';
  const blob = Utilities.newBlob(json, 'application/json', fileName);
  folder.createFile(blob);
}

function fileExistsByName_(folder, fileName) {
  return folder.getFilesByName(fileName).hasNext();
}

function floorDateToMinutes_(date, minutes) {
  const bucketMs = minutes * 60 * 1000;
  return new Date(Math.floor(date.getTime() / bucketMs) * bucketMs);
}

function addMinutes_(date, minutes) {
  return new Date(date.getTime() + minutes * 60 * 1000);
}

function formatUtcCompact_(date) {
  return Utilities.formatDate(date, 'UTC', "yyyyMMdd'T'HHmm'Z'");
}
