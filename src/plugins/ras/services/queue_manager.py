#!/usr/bin/env python3
"""
RAS CPER Queue Manager

Manages prioritized queue for CPER record processing with:
- Priority-based queuing (Critical > Warning > OK)
- Background processing worker
- Deferred processing for low-priority records
- Queue statistics and monitoring
"""

import logging
import threading
import time
from typing import Dict, Any, List, Optional, Callable
from datetime import datetime, timezone
from enum import Enum
from queue import PriorityQueue, Empty
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


class CPERPriority(Enum):
    """CPER processing priority levels"""
    CRITICAL = 0  # Highest priority
    WARNING = 1   # Medium priority
    OK = 2        # Low priority
    DEFERRED = 3  # Deferred processing


@dataclass(order=True)
class CPERQueueItem:
    """Item in CPER processing queue"""
    priority: int = field(compare=True)
    timestamp: float = field(compare=True)
    cper_data: Dict[str, Any] = field(compare=False, default_factory=dict)
    manager_id: str = field(compare=False, default="")
    entry_id: Optional[str] = field(compare=False, default=None)
    metadata: Dict[str, Any] = field(compare=False, default_factory=dict)


class CPERQueueManager:
    """
    Manages CPER record processing queue with prioritization.
    
    Features:
    - Priority-based queuing
    - Background processing thread
    - Deferred processing for low-priority items
    - Queue statistics
    - Custom processing handlers
    """
    
    def __init__(
        self,
        max_queue_size: int = 1000,
        worker_count: int = 2,
        defer_threshold: int = 100,
        enable_deferred_processing: bool = True
    ):
        """
        Initialize CPER queue manager.
        
        Args:
            max_queue_size: Maximum queue size
            worker_count: Number of background worker threads
            defer_threshold: Queue size threshold for deferring low-priority items
            enable_deferred_processing: Enable deferred processing
        """
        self.max_queue_size = max_queue_size
        self.worker_count = worker_count
        self.defer_threshold = defer_threshold
        self.enable_deferred_processing = enable_deferred_processing
        
        # Priority queue for CPER records
        self.queue = PriorityQueue(maxsize=max_queue_size)
        
        # Deferred queue for low-priority items
        self.deferred_queue = PriorityQueue(maxsize=max_queue_size)
        
        # Worker threads
        self.workers: List[threading.Thread] = []
        self.running = False
        self.processing_lock = threading.Lock()
        
        # Processing handlers
        self.handlers: List[Callable[[CPERQueueItem], None]] = []
        
        # Statistics
        self.stats = {
            "total_queued": 0,
            "total_processed": 0,
            "total_deferred": 0,
            "total_failed": 0,
            "critical_processed": 0,
            "warning_processed": 0,
            "ok_processed": 0,
            "deferred_processed": 0,
            "queue_overflows": 0,
            "processing_errors": 0
        }
        
        logger.info(f"CPER Queue Manager initialized (workers={worker_count}, "
                   f"max_size={max_queue_size}, defer_threshold={defer_threshold})")
    
    def start(self):
        """Start background worker threads"""
        if self.running:
            logger.warning("Queue manager already running")
            return
        
        self.running = True
        
        # Start worker threads
        for i in range(self.worker_count):
            worker = threading.Thread(
                target=self._worker_loop,
                name=f"CPERWorker-{i}",
                daemon=True
            )
            worker.start()
            self.workers.append(worker)
            logger.info(f"Started worker thread: {worker.name}")
        
        # Start deferred processing thread
        if self.enable_deferred_processing:
            deferred_worker = threading.Thread(
                target=self._deferred_worker_loop,
                name="CPERDeferredWorker",
                daemon=True
            )
            deferred_worker.start()
            self.workers.append(deferred_worker)
            logger.info("Started deferred processing worker")
    
    def stop(self):
        """Stop background worker threads"""
        if not self.running:
            return
        
        logger.info("Stopping CPER queue manager...")
        self.running = False
        
        # Wait for workers to finish
        for worker in self.workers:
            worker.join(timeout=5.0)
        
        self.workers.clear()
        logger.info("CPER queue manager stopped")
    
    def register_handler(self, handler: Callable[[CPERQueueItem], None]):
        """
        Register a processing handler.
        
        Args:
            handler: Function to process CPER queue items
        """
        self.handlers.append(handler)
        logger.info(f"Registered processing handler: {handler.__name__}")
    
    def enqueue_cper(
        self,
        manager_id: str,
        cper_data: Dict[str, Any],
        severity: str = "OK",
        entry_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Enqueue CPER record for processing.
        
        Args:
            manager_id: Manager ID
            cper_data: CPER record data
            severity: Severity level (Critical, Warning, OK)
            entry_id: LogEntry ID if already created
            metadata: Additional metadata
            
        Returns:
            bool: True if enqueued successfully
        """
        # Map severity to priority
        priority_map = {
            "Critical": CPERPriority.CRITICAL.value,
            "Warning": CPERPriority.WARNING.value,
            "OK": CPERPriority.OK.value
        }
        priority = priority_map.get(severity, CPERPriority.OK.value)
        
        # Check if we should defer low-priority items
        if (self.enable_deferred_processing and 
            priority == CPERPriority.OK.value and 
            self.queue.qsize() >= self.defer_threshold):
            
            return self._enqueue_deferred(
                manager_id, cper_data, entry_id, metadata or {}
            )
        
        # Create queue item
        item = CPERQueueItem(
            priority=priority,
            timestamp=time.time(),
            cper_data=cper_data,
            manager_id=manager_id,
            entry_id=entry_id,
            metadata=metadata or {}
        )
        
        # Try to enqueue
        try:
            self.queue.put_nowait(item)
            self.stats["total_queued"] += 1
            logger.debug(f"Enqueued CPER (priority={priority}, severity={severity})")
            return True
        except Exception as e:
            logger.error(f"Failed to enqueue CPER: {e}")
            self.stats["queue_overflows"] += 1
            
            # Try deferred queue as fallback
            if self.enable_deferred_processing:
                return self._enqueue_deferred(
                    manager_id, cper_data, entry_id, metadata or {}
                )
            
            return False
    
    def _enqueue_deferred(
        self,
        manager_id: str,
        cper_data: Dict[str, Any],
        entry_id: Optional[str],
        metadata: Dict[str, Any]
    ) -> bool:
        """Enqueue item to deferred queue"""
        item = CPERQueueItem(
            priority=CPERPriority.DEFERRED.value,
            timestamp=time.time(),
            cper_data=cper_data,
            manager_id=manager_id,
            entry_id=entry_id,
            metadata=metadata
        )
        
        try:
            self.deferred_queue.put_nowait(item)
            self.stats["total_deferred"] += 1
            logger.debug("Enqueued CPER to deferred queue")
            return True
        except Exception as e:
            logger.error(f"Failed to enqueue to deferred queue: {e}")
            return False
    
    def _worker_loop(self):
        """Background worker loop for processing CPER records"""
        logger.info(f"Worker {threading.current_thread().name} started")
        
        while self.running:
            try:
                # Get item from queue with timeout
                item = self.queue.get(timeout=1.0)
                
                # Process item
                self._process_item(item)
                
                # Mark as done
                self.queue.task_done()
                
            except Empty:
                # No items in queue, continue
                continue
            except Exception as e:
                logger.error(f"Worker error: {e}", exc_info=True)
                self.stats["processing_errors"] += 1
        
        logger.info(f"Worker {threading.current_thread().name} stopped")
    
    def _deferred_worker_loop(self):
        """Background worker for deferred processing"""
        logger.info("Deferred worker started")
        
        while self.running:
            try:
                # Only process deferred items when main queue is not too full
                if self.queue.qsize() < self.defer_threshold // 2:
                    item = self.deferred_queue.get(timeout=5.0)
                    self._process_item(item)
                    self.deferred_queue.task_done()
                else:
                    # Main queue is busy, wait
                    time.sleep(2.0)
                    
            except Empty:
                # No deferred items, wait
                time.sleep(5.0)
            except Exception as e:
                logger.error(f"Deferred worker error: {e}", exc_info=True)
                self.stats["processing_errors"] += 1
        
        logger.info("Deferred worker stopped")
    
    def _process_item(self, item: CPERQueueItem):
        """Process a CPER queue item"""
        try:
            # Update statistics
            self.stats["total_processed"] += 1
            
            if item.priority == CPERPriority.CRITICAL.value:
                self.stats["critical_processed"] += 1
            elif item.priority == CPERPriority.WARNING.value:
                self.stats["warning_processed"] += 1
            elif item.priority == CPERPriority.OK.value:
                self.stats["ok_processed"] += 1
            elif item.priority == CPERPriority.DEFERRED.value:
                self.stats["deferred_processed"] += 1
            
            # Call all registered handlers
            for handler in self.handlers:
                try:
                    handler(item)
                except Exception as e:
                    logger.error(f"Handler {handler.__name__} failed: {e}", exc_info=True)
                    self.stats["total_failed"] += 1
            
            logger.debug(f"Processed CPER item (priority={item.priority}, "
                        f"manager={item.manager_id})")
            
        except Exception as e:
            logger.error(f"Failed to process CPER item: {e}", exc_info=True)
            self.stats["total_failed"] += 1
    
    def get_stats(self) -> Dict[str, Any]:
        """Get queue statistics"""
        return {
            **self.stats,
            "queue_size": self.queue.qsize(),
            "deferred_queue_size": self.deferred_queue.qsize(),
            "worker_count": len([w for w in self.workers if w.is_alive()]),
            "running": self.running
        }
    
    def get_queue_status(self) -> Dict[str, Any]:
        """Get detailed queue status"""
        return {
            "main_queue": {
                "size": self.queue.qsize(),
                "max_size": self.max_queue_size,
                "utilization": f"{(self.queue.qsize() / self.max_queue_size * 100):.1f}%"
            },
            "deferred_queue": {
                "size": self.deferred_queue.qsize(),
                "max_size": self.max_queue_size,
                "utilization": f"{(self.deferred_queue.qsize() / self.max_queue_size * 100):.1f}%"
            },
            "workers": {
                "total": self.worker_count + (1 if self.enable_deferred_processing else 0),
                "active": len([w for w in self.workers if w.is_alive()])
            },
            "statistics": self.get_stats()
        }
    
    def clear_queues(self):
        """Clear all queues (for testing/maintenance)"""
        with self.processing_lock:
            while not self.queue.empty():
                try:
                    self.queue.get_nowait()
                    self.queue.task_done()
                except Empty:
                    break
            
            while not self.deferred_queue.empty():
                try:
                    self.deferred_queue.get_nowait()
                    self.deferred_queue.task_done()
                except Empty:
                    break
            
            logger.info("Queues cleared")
