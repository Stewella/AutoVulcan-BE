from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.orm import Session
from db import get_db
from schemas import RunRequest, RunResponse, CallGraphResponse
from services.pipeline import new_execution_id, schedule_pipeline
from auth.jwt import get_current_user
from datetime import datetime
from fastapi import File, UploadFile, Form
from typing import Optional
import os
import zipfile
import re
import json
from crud import create_execution
from models import Execution
from fastapi import Body, HTTPException
from services.evosuite_client import run_evosuite_in_docker

router = APIRouter(prefix="/analysis", tags=["analysis"])

# -----------------------------
# Module-level constants & helpers
# -----------------------------
ALLOWED_ZIP_TYPES = {
    "application/zip",
    "application/x-zip-compressed",
    "multipart/x-zip",
}

# Loader to parse external analysis JSON into the call graph format used here
def load_call_graph_from_json(path: str) -> Optional[dict]:
    try:
        with open(path, "r") as f:
            data = json.load(f)
        cg = data.get("callGraph")
        if isinstance(cg, dict) and "nodes" in cg and "edges" in cg:
            return {"callGraph": cg}
    except Exception:
        pass
    return None

DEFAULT_SAMPLE_CALL_GRAPH = {
    "callGraph": {
        "nodes": [
            {"id": "n1",  "label": "MainApp.main()", "type": "entry"},
            {"id": "n2",  "label": "ServiceB.runTask()", "type": "intermediate"},
            {"id": "n3",  "label": "Repository.load()", "type": "intermediate"},
            {"id": "n4",  "label": "Repository.<init>()", "type": "intermediate"},
            {"id": "n5",  "label": "ServiceB.<init>()", "type": "intermediate"},
            {"id": "n6",  "label": "ServiceA.processData()", "type": "intermediate"},
            {"id": "n7",  "label": "Utils.log()", "type": "intermediate"},
            {"id": "n8",  "label": "Utils.printSummary()", "type": "intermediate"},
            {"id": "n9",  "label": "Repository.save()", "type": "intermediate"},
            {"id": "n10", "label": "PrintStream.println()", "type": "intermediate"},
            {"id": "n11", "label": "ServiceB.transform()", "type": "intermediate"},
            {"id": "n12", "label": "String.toUpperCase()", "type": "intermediate"},
            {"id": "n13", "label": "Object.<init>()", "type": "intermediate"},
            {"id": "n14", "label": "ServiceA.<init>()", "type": "intermediate"},
        ],
        "edges": [
            {"source": "n2", "target": "n3"},
            {"source": "n1", "target": "n4"},
            {"source": "n5", "target": "n13"},
            {"source": "n6", "target": "n7"},
            {"source": "n1", "target": "n5"},
            {"source": "n1", "target": "n2"},
            {"source": "n1", "target": "n8"},
            {"source": "n9", "target": "n7"},
            {"source": "n1", "target": "n6"},
            {"source": "n8", "target": "n10"},
            {"source": "n6", "target": "n10"},
            {"source": "n2", "target": "n11"},
            {"source": "n2", "target": "n9"},
            {"source": "n3", "target": "n7"},
            {"source": "n1", "target": "n10"},
            {"source": "n11", "target": "n12"},
            {"source": "n2", "target": "n10"},
            {"source": "n7", "target": "n10"},
            {"source": "n4", "target": "n13"},
            {"source": "n1", "target": "n14"},
            {"source": "n14", "target": "n13"},
        ],
    }
}

PETSHOP_SAMPLE_CALL_GRAPH = {
  "callGraph": {
    "nodes": [
      { "id": "n13", "label": "com.petstore.domain.Customer.getName()", "type": "intermediate" },
      { "id": "n50", "label": "com.petstore.api.PetStoreApplication.demonstrateVulnerableChains()", "type": "intermediate" },
      { "id": "n19", "label": "com.petstore.api.controller.PetController.batchProcess()", "type": "intermediate" },
      { "id": "n34", "label": "com.petstore.service.PetService.createCustomPetListing()", "type": "intermediate" },
      { "id": "n40", "label": "com.petstore.api.controller.OrderController.createOrder()", "type": "intermediate" },
      { "id": "n56", "label": "java.lang.String.format()", "type": "intermediate" },
      { "id": "n32", "label": "com.petstore.domain.Order.getStatus()", "type": "intermediate" },
      { "id": "n35", "label": "com.petstore.data.PetRepository.generatePetListing()", "type": "intermediate" },
      { "id": "n74", "label": "com.petstore.domain.Pet.getName()", "type": "intermediate" },
      { "id": "n86", "label": "com.petstore.api.controller.CustomerController.getAllCustomers()", "type": "intermediate" },
      { "id": "n65", "label": "java.lang.StringBuilder.append()", "type": "intermediate" },
      { "id": "n24", "label": "com.petstore.data.TemplateProcessor.<init>()", "type": "intermediate" },
      { "id": "n42", "label": "com.petstore.service.CustomerService.<init>()", "type": "intermediate" },
      { "id": "n44", "label": "com.petstore.api.PetStoreApplication.main()", "type": "entry" },
      { "id": "n66", "label": "com.petstore.data.CustomerRepository.generateWelcomeMessage()", "type": "intermediate" },
      { "id": "n62", "label": "com.petstore.data.OrderRepository.<init>()", "type": "intermediate" },
      { "id": "n49", "label": "com.petstore.api.PetStoreApplication.demonstrateNormalOperations()", "type": "intermediate" },
      { "id": "n2", "label": "com.petstore.domain.Customer.<init>()", "type": "intermediate" },
      { "id": "n29", "label": "com.petstore.domain.Order.getPetId()", "type": "intermediate" },
      { "id": "n9", "label": "com.petstore.api.controller.OrderController.confirmOrder()", "type": "intermediate" },
      { "id": "n11", "label": "com.petstore.data.CustomerRepository.formatNotification()", "type": "intermediate" },
      { "id": "n15", "label": "java.util.Map.values()", "type": "intermediate" },
      { "id": "n55", "label": "java.lang.Integer.valueOf()", "type": "intermediate" },
      { "id": "n23", "label": "java.util.concurrent.ConcurrentHashMap.<init>()", "type": "intermediate" },
      { "id": "n61", "label": "com.petstore.api.controller.PetController.createCustomListing()", "type": "intermediate" },
      { "id": "n16", "label": "java.util.ArrayList.<init>()", "type": "intermediate" },
      { "id": "n25", "label": "com.petstore.data.OrderRepository.generateOrderConfirmation()", "type": "intermediate" },
      { "id": "n63", "label": "com.petstore.service.OrderService.generateCompleteOrderReport()", "type": "intermediate" },
      { "id": "n36", "label": "com.petstore.service.CustomerService.getAllCustomers()", "type": "intermediate" },
      { "id": "n48", "label": "com.petstore.api.controller.OrderController.<init>()", "type": "intermediate" },
      { "id": "n75", "label": "com.petstore.domain.Pet.getSpecies()", "type": "intermediate" },
      { "id": "n39", "label": "com.petstore.service.PetService.<init>()", "type": "intermediate" },
      { "id": "n64", "label": "java.lang.StringBuilder.<init>()", "type": "intermediate" },
      { "id": "n70", "label": "com.petstore.data.PetRepository.<init>()", "type": "intermediate" },
      { "id": "n59", "label": "com.petstore.domain.Order.<init>()", "type": "intermediate" },
      { "id": "n1", "label": "com.petstore.data.CustomerRepository.initializeSampleData()", "type": "intermediate" },
      { "id": "n7", "label": "com.petstore.service.PetService.getAllPets()", "type": "intermediate" },
      { "id": "n4", "label": "com.petstore.data.PetRepository.savePet()", "type": "intermediate" },
      { "id": "n26", "label": "java.util.HashMap.<init>()", "type": "intermediate" },
      { "id": "n14", "label": "com.petstore.data.TemplateProcessor.formatMessage()", "type": "intermediate" },
      { "id": "n30", "label": "com.petstore.domain.Order.getTotalAmount()", "type": "intermediate" },
      { "id": "n72", "label": "com.petstore.data.PetRepository.initializeSampleData()", "type": "intermediate" },
      { "id": "n69", "label": "com.petstore.service.PetService.generatePetAdvertisement()", "type": "intermediate" },
      { "id": "n41", "label": "com.petstore.service.OrderService.createOrder()", "type": "intermediate" },
      { "id": "n77", "label": "com.petstore.domain.Pet.getStatus()", "type": "intermediate" },
      { "id": "n37", "label": "com.petstore.data.CustomerRepository.findAll()", "type": "intermediate" },
      { "id": "n58", "label": "com.petstore.domain.Pet.getPrice()", "type": "intermediate" },
      { "id": "n22", "label": "java.lang.Object.<init>()", "type": "intermediate" },
      { "id": "n3", "label": "com.petstore.data.CustomerRepository.saveCustomer()", "type": "intermediate" },
      { "id": "n54", "label": "java.lang.Math.random()", "type": "intermediate" },
      { "id": "n85", "label": "com.petstore.api.controller.PetController.getAllPets()", "type": "intermediate" },
      { "id": "n20", "label": "com.petstore.service.PetService.batchProcessPetDescriptions()", "type": "intermediate" },
      { "id": "n76", "label": "com.petstore.domain.Pet.getBreed()", "type": "intermediate" },
      { "id": "n53", "label": "com.petstore.data.OrderRepository.saveOrder()", "type": "intermediate" },
      { "id": "n68", "label": "java.lang.StringBuilder.toString()", "type": "intermediate" },
      { "id": "n12", "label": "com.petstore.data.CustomerRepository.findById()", "type": "intermediate" },
      { "id": "n47", "label": "com.petstore.api.controller.CustomerController.<init>()", "type": "intermediate" },
      { "id": "n33", "label": "com.petstore.data.TemplateProcessor.processTemplate()", "type": "intermediate" },
      { "id": "n52", "label": "com.petstore.service.CustomerService.sendCustomNotification()", "type": "intermediate" },
      { "id": "n31", "label": "java.lang.String.valueOf()", "type": "intermediate" },
      { "id": "n57", "label": "java.time.LocalDateTime.now()", "type": "intermediate" },
      { "id": "n71", "label": "com.petstore.api.controller.PetController.getPetAdvertisement()", "type": "intermediate" },
      { "id": "n81", "label": "java.util.List.iterator()", "type": "intermediate" },
      { "id": "n67", "label": "com.petstore.data.PetRepository.generatePetDescription()", "type": "intermediate" },
      { "id": "n6", "label": "java.util.Map.put()", "type": "intermediate" },
      { "id": "n80", "label": "com.petstore.api.controller.OrderController.getCompleteReport()", "type": "intermediate" },
      { "id": "n87", "label": "com.petstore.domain.Customer.getEmail()", "type": "intermediate" },
      { "id": "n18", "label": "java.util.Map.get()", "type": "intermediate" },
      { "id": "n43", "label": "com.petstore.data.PetRepository.findById()", "type": "intermediate" },
      { "id": "n5", "label": "com.petstore.domain.Pet.getId()", "type": "intermediate" },
      { "id": "n27", "label": "com.petstore.domain.Order.getId()", "type": "intermediate" },
      { "id": "n84", "label": "com.petstore.domain.Customer.getId()", "type": "intermediate" },
      { "id": "n46", "label": "java.io.PrintStream.println()", "type": "intermediate" },
      { "id": "n10", "label": "com.petstore.service.OrderService.processOrderConfirmation()", "type": "intermediate" },
      { "id": "n82", "label": "java.util.Iterator.hasNext()", "type": "intermediate" },
      { "id": "n17", "label": "com.petstore.data.OrderRepository.findById()", "type": "intermediate" },
      { "id": "n78", "label": "org.apache.commons.text.StringSubstitutor.<init>()", "type": "intermediate" },
      { "id": "n8", "label": "com.petstore.data.PetRepository.findAll()", "type": "intermediate" },
      { "id": "n45", "label": "java.io.PrintStream.println()", "type": "intermediate" },
      { "id": "n79", "label": "org.apache.commons.text.StringSubstitutor.replace()", "type": "intermediate" },
      { "id": "n38", "label": "com.petstore.api.controller.PetController.<init>()", "type": "intermediate" },
      { "id": "n28", "label": "com.petstore.domain.Order.getCustomerId()", "type": "intermediate" },
      { "id": "n51", "label": "com.petstore.api.controller.CustomerController.sendNotification()", "type": "intermediate" },
      { "id": "n88", "label": "java.util.Arrays.asList()", "type": "intermediate" },
      { "id": "n73", "label": "com.petstore.domain.Pet.<init>()", "type": "intermediate" },
      { "id": "n21", "label": "com.petstore.data.CustomerRepository.<init>()", "type": "intermediate" },
      { "id": "n83", "label": "java.util.Iterator.next()", "type": "intermediate" },
      { "id": "n60", "label": "com.petstore.service.OrderService.<init>()", "type": "intermediate" }
    ],
    "edges": [
      { "source": "n1", "target": "n2" },
      { "source": "n1", "target": "n3" },
      { "source": "n1", "target": "n2" },
      { "source": "n1", "target": "n3" },
      { "source": "n4", "target": "n5" },
      { "source": "n4", "target": "n6" },
      { "source": "n7", "target": "n8" },
      { "source": "n9", "target": "n10" },
      { "source": "n11", "target": "n12" },
      { "source": "n11", "target": "n13" },
      { "source": "n11", "target": "n14" },
      { "source": "n8", "target": "n15" },
      { "source": "n8", "target": "n16" },
      { "source": "n17", "target": "n18" },
      { "source": "n19", "target": "n20" },
      { "source": "n12", "target": "n18" },
      { "source": "n21", "target": "n22" },
      { "source": "n21", "target": "n23" },
      { "source": "n21", "target": "n24" },
      { "source": "n21", "target": "n1" },
      { "source": "n25", "target": "n17" },
      { "source": "n25", "target": "n26" },
      { "source": "n25", "target": "n27" },
      { "source": "n25", "target": "n6" },
      { "source": "n25", "target": "n28" },
      { "source": "n25", "target": "n6" },
      { "source": "n25", "target": "n29" },
      { "source": "n25", "target": "n6" },
      { "source": "n25", "target": "n30" },
      { "source": "n25", "target": "n31" },
      { "source": "n25", "target": "n6" },
      { "source": "n25", "target": "n32" },
      { "source": "n25", "target": "n6" },
      { "source": "n25", "target": "n33" },
      { "source": "n34", "target": "n35" },
      { "source": "n36", "target": "n37" },
      { "source": "n38", "target": "n22" },
      { "source": "n38", "target": "n39" },
      { "source": "n40", "target": "n41" },
      { "source": "n42", "target": "n22" },
      { "source": "n42", "target": "n21" },
      { "source": "n43", "target": "n18" },
      { "source": "n44", "target": "n45" },
      { "source": "n44", "target": "n45" },
      { "source": "n44", "target": "n46" },
      { "source": "n44", "target": "n38" },
      { "source": "n44", "target": "n47" },
      { "source": "n44", "target": "n48" },
      { "source": "n44", "target": "n49" },
      { "source": "n44", "target": "n46" },
      { "source": "n44", "target": "n45" },
      { "source": "n44", "target": "n50" },
      { "source": "n44", "target": "n46" },
      { "source": "n44", "target": "n45" },
      { "source": "n44", "target": "n45" },
      { "source": "n51", "target": "n52" },
      { "source": "n53", "target": "n27" },
      { "source": "n53", "target": "n6" },
      { "source": "n41", "target": "n12" },
      { "source": "n41", "target": "n43" },
      { "source": "n41", "target": "n54" },
      { "source": "n41", "target": "n55" },
      { "source": "n41", "target": "n56" },
      { "source": "n41", "target": "n57" },
      { "source": "n41", "target": "n58" },
      { "source": "n41", "target": "n59" },
      { "source": "n41", "target": "n53" },
      { "source": "n48", "target": "n22" },
      { "source": "n48", "target": "n60" },
      { "source": "n61", "target": "n34" },
      { "source": "n62", "target": "n22" },
      { "source": "n62", "target": "n23" },
      { "source": "n62", "target": "n24" },
      { "source": "n52", "target": "n11" },
      { "source": "n63", "target": "n17" },
      { "source": "n63", "target": "n64" },
      { "source": "n63", "target": "n65" },
      { "source": "n63", "target": "n25" },
      { "source": "n63", "target": "n65" },
      { "source": "n63", "target": "n65" },
      { "source": "n63", "target": "n28" },
      { "source": "n63", "target": "n66" },
      { "source": "n63", "target": "n65" },
      { "source": "n63", "target": "n65" },
      { "source": "n63", "target": "n29" },
      { "source": "n63", "target": "n43" },
      { "source": "n63", "target": "n67" },
      { "source": "n63", "target": "n65" },
      { "source": "n63", "target": "n65" },
      { "source": "n63", "target": "n68" },
      { "source": "n69", "target": "n43" },
      { "source": "n69", "target": "n67" },
      { "source": "n24", "target": "n22" },
      { "source": "n37", "target": "n15" },
      { "source": "n37", "target": "n16" },
      { "source": "n39", "target": "n22" },
      { "source": "n39", "target": "n70" },
      { "source": "n59", "target": "n22" },
      { "source": "n71", "target": "n69" },
      { "source": "n72", "target": "n73" },
      { "source": "n72", "target": "n4" },
      { "source": "n72", "target": "n73" },
      { "source": "n72", "target": "n4" },
      { "source": "n72", "target": "n73" },
      { "source": "n72", "target": "n4" },
      { "source": "n67", "target": "n26" },
      { "source": "n67", "target": "n74" },
      { "source": "n67", "target": "n6" },
      { "source": "n67", "target": "n75" },
      { "source": "n67", "target": "n6" },
      { "source": "n67", "target": "n76" },
      { "source": "n67", "target": "n6" },
      { "source": "n67", "target": "n58" },
      { "source": "n67", "target": "n31" },
      { "source": "n67", "target": "n6" },
      { "source": "n67", "target": "n77" },
      { "source": "n67", "target": "n6" },
      { "source": "n67", "target": "n33" },
      { "source": "n35", "target": "n43" },
      { "source": "n35", "target": "n67" },
      { "source": "n33", "target": "n78" },
      { "source": "n33", "target": "n79" },
      { "source": "n80", "target": "n63" },
      { "source": "n20", "target": "n64" },
      { "source": "n20", "target": "n81" },
      { "source": "n20", "target": "n82" },
      { "source": "n20", "target": "n83" },
      { "source": "n20", "target": "n35" },
      { "source": "n20", "target": "n65" },
      { "source": "n20", "target": "n65" },
      { "source": "n20", "target": "n68" },
      { "source": "n3", "target": "n84" },
      { "source": "n3", "target": "n6" },
      { "source": "n73", "target": "n22" },
      { "source": "n70", "target": "n22" },
      { "source": "n70", "target": "n23" },
      { "source": "n70", "target": "n24" },
      { "source": "n70", "target": "n72" },
      { "source": "n60", "target": "n22" },
      { "source": "n60", "target": "n62" },
      { "source": "n60", "target": "n70" },
      { "source": "n60", "target": "n21" },
      { "source": "n49", "target": "n45" },
      { "source": "n49", "target": "n45" },
      { "source": "n49", "target": "n85" },
      { "source": "n49", "target": "n81" },
      { "source": "n49", "target": "n82" },
      { "source": "n49", "target": "n83" },
      { "source": "n49", "target": "n74" },
      { "source": "n49", "target": "n75" },
      { "source": "n49", "target": "n45" },
      { "source": "n49", "target": "n45" },
      { "source": "n49", "target": "n86" },
      { "source": "n49", "target": "n81" },
      { "source": "n49", "target": "n82" },
      { "source": "n49", "target": "n83" },
      { "source": "n49", "target": "n13" },
      { "source": "n49", "target": "n87" },
      { "source": "n49", "target": "n45" },
      { "source": "n49", "target": "n45" },
      { "source": "n49", "target": "n40" },
      { "source": "n49", "target": "n27" },
      { "source": "n49", "target": "n45" },
      { "source": "n86", "target": "n36" },
      { "source": "n66", "target": "n12" },
      { "source": "n66", "target": "n26" },
      { "source": "n66", "target": "n13" },
      { "source": "n66", "target": "n6" },
      { "source": "n66", "target": "n87" },
      { "source": "n66", "target": "n6" },
      { "source": "n66", "target": "n33" },
      { "source": "n47", "target": "n22" },
      { "source": "n47", "target": "n42" },
      { "source": "n85", "target": "n7" },
      { "source": "n14", "target": "n26" },
      { "source": "n14", "target": "n6" },
      { "source": "n14", "target": "n33" },
      { "source": "n2", "target": "n22" },
      { "source": "n50", "target": "n45" },
      { "source": "n50", "target": "n45" },
      { "source": "n50", "target": "n71" },
      { "source": "n50", "target": "n45" },
      { "source": "n50", "target": "n45" },
      { "source": "n50", "target": "n45" },
      { "source": "n50", "target": "n61" },
      { "source": "n50", "target": "n45" },
      { "source": "n50", "target": "n45" },
      { "source": "n50", "target": "n45" },
      { "source": "n50", "target": "n51" },
      { "source": "n50", "target": "n45" },
      { "source": "n50", "target": "n45" },
      { "source": "n50", "target": "n45" },
      { "source": "n50", "target": "n40" },
      { "source": "n50", "target": "n27" },
      { "source": "n50", "target": "n9" },
      { "source": "n50", "target": "n45" },
      { "source": "n50", "target": "n45" },
      { "source": "n50", "target": "n45" },
      { "source": "n50", "target": "n27" },
      { "source": "n50", "target": "n80" },
      { "source": "n50", "target": "n45" },
      { "source": "n50", "target": "n45" },
      { "source": "n50", "target": "n45" },
      { "source": "n50", "target": "n45" },
      { "source": "n50", "target": "n88" },
      { "source": "n50", "target": "n19" },
      { "source": "n50", "target": "n45" },
      { "source": "n50", "target": "n45" },
      { "source": "n50", "target": "n45" },
      { "source": "n50", "target": "n45" },
      { "source": "n10", "target": "n25" }
    ]
  }
};


DUMMYAPPS2_CALL_GRAPH = {
  "callGraph": {
    "nodes": [
      { "id": "n18", "label": "com.example.service.StageTwo.refine()", "type": "intermediate" },
      { "id": "n9",  "label": "java.lang.Object.<init>()", "type": "intermediate" },
      { "id": "n19", "label": "com.example.service.StageThree.finalizeProcessing()", "type": "intermediate" },
      { "id": "n11", "label": "com.example.service.BusinessService.processInput()", "type": "intermediate" },
      { "id": "n13", "label": "com.example.service.StageOne.transform()", "type": "intermediate" },
      { "id": "n3",  "label": "java.lang.String.trim()", "type": "intermediate" },
      { "id": "n4",  "label": "com.example.core.VulnerableTemplateEngine.renderTemplate()", "type": "intermediate" },
      { "id": "n6",  "label": "org.apache.commons.text.StringSubstitutor.<init>()", "type": "vulnerable" },
      { "id": "n14", "label": "com.example.core.StringUtilsCore.normalize()", "type": "intermediate" },
      { "id": "n12", "label": "com.example.service.DataPipeline.startPipeline()", "type": "intermediate" },
      { "id": "n5",  "label": "org.apache.commons.text.lookup.StringLookupFactory.interpolatorStringLookup()", "type": "intermediate" },
      { "id": "n8",  "label": "com.example.service.BusinessService.<init>()", "type": "intermediate" },
      { "id": "n7",  "label": "org.apache.commons.text.StringSubstitutor.replace()", "type": "vulnerable" },
      { "id": "n17", "label": "java.io.PrintStream.println()", "type": "intermediate" },
      { "id": "n10", "label": "com.example.core.VulnerableTemplateEngine.<init>()", "type": "intermediate" },
      { "id": "n15", "label": "java.lang.String.toLowerCase()", "type": "intermediate" },
      { "id": "n1",  "label": "com.example.core.StringUtilsCore.sanitize()", "type": "intermediate" },
      { "id": "n2",  "label": "java.lang.String.replaceAll()", "type": "intermediate" },
      { "id": "n16", "label": "com.example.app.MainApplication.main()", "type": "entry" }
    ],

    "edges": [
      { "source": "n1",  "target": "n2" },
      { "source": "n1",  "target": "n3" },
      { "source": "n4",  "target": "n5" },
      { "source": "n4",  "target": "n6" },
      { "source": "n4",  "target": "n7" },
      { "source": "n8",  "target": "n9" },
      { "source": "n10", "target": "n9" },
      { "source": "n11", "target": "n12" },
      { "source": "n12", "target": "n13" },
      { "source": "n14", "target": "n15" },
      { "source": "n16", "target": "n8" },
      { "source": "n16", "target": "n11" },
      { "source": "n16", "target": "n17" },
      { "source": "n13", "target": "n1" },
      { "source": "n13", "target": "n18" },
      { "source": "n18", "target": "n14" },
      { "source": "n18", "target": "n19" },
      { "source": "n19", "target": "n10" },
      { "source": "n19", "target": "n4" }
    ]
  }
}

CALL_GRAPH_JSON_PATH = os.getenv("CALL_GRAPH_JSON_PATH", "/Users/bytedance/Downloads/analysis-result.json")
_loaded_cg = load_call_graph_from_json(CALL_GRAPH_JSON_PATH)
SAMPLE_CALL_GRAPH = _loaded_cg or DEFAULT_SAMPLE_CALL_GRAPH


def normalize_cve(cve: str) -> str:
    """Return CVE as string (already validated and normalized upstream)."""
    return cve


def schedule_exec(background_tasks: BackgroundTasks, exec_id: str, request_obj: dict) -> None:
    """Schedule the pipeline execution in the background."""
    background_tasks.add_task(schedule_pipeline, exec_id, request_obj)


def make_request_obj(
    *,
    source_type: str,
    target_cve: str,
    target_method: Optional[str],
    target_line: Optional[int],
    timeout_seconds: int,
    submitted_by: Optional[str],
    submitted_by_user_id: Optional[int] = None,
    branch: Optional[str] = None,
    repository_url: Optional[str] = None,
    source_path: Optional[str] = None,
    skip_evosuite: Optional[bool] = False,
    skip_core_engine: Optional[bool] = False,
) -> dict:
    """Build a standardized request object for the pipeline."""
    base = {
        "source_type": source_type,
        "target_cve": normalize_cve(target_cve),
        "target_method": target_method,
        "target_line": target_line,
        "timeout_seconds": timeout_seconds,
        "submitted_by": submitted_by,
        "submitted_by_user_id": submitted_by_user_id,
        "skip_evosuite": bool(skip_evosuite),
        "skip_core_engine": bool(skip_core_engine),
    }
    if branch:
        base["branch"] = branch
    if repository_url:
        base["repository_url"] = repository_url
    if source_path:
        base["source_path"] = source_path
    return base


def ensure_execution_dir(exec_id: str) -> str:
    """Create and return the base execution directory path for a given execution id."""
    base_dir = os.path.join("/tmp/executions", exec_id)
    os.makedirs(base_dir, exist_ok=True)
    return base_dir


def save_zip(file: UploadFile, zip_path: str) -> None:
    """Save uploaded ZIP file to the specified path in chunks."""
    with open(zip_path, "wb") as out:
        while True:
            chunk = file.file.read(8192)
            if not chunk:
                break
            out.write(chunk)


def extract_zip(zip_path: str, extract_dir: str) -> None:
    """Extract the ZIP file to the given directory, raising HTTP 400 for invalid archives."""
    os.makedirs(extract_dir, exist_ok=True)
    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(extract_dir)
    except zipfile.BadZipFile:
        raise HTTPException(status_code=400, detail="Invalid ZIP file")


# -----------------------------
# Endpoints
# -----------------------------
@router.post("/run", response_model=RunResponse, summary="Start analysis run")
def run_analysis(
    req: RunRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Start an analysis using a flexible JSON body (RunRequest)."""
    exec_id = new_execution_id()
    # Persist execution immediately (optional for /run)
    payload = {**req.dict(), "submitted_by": current_user.get("username"), "submitted_by_user_id": current_user.get("id")}
    create_execution(db, exec_id, payload)
    # schedule pipeline background job which will persist logs/result to DB
    schedule_exec(background_tasks, exec_id, payload)
    return RunResponse(
        status="success",
        execution_id=exec_id,
        message="SEIGE analysis started",
        started_at=datetime.utcnow(),
    )


@router.get("/graph", response_model=CallGraphResponse, summary="Get call graph")
def get_call_graph(execution_id: Optional[str] = None, db: Session = Depends(get_db)):
    """Return a dummy call graph based on the original request payload.

    If the repo matches Stewella/DummyApps2, return DUMMYAPPS2_CALL_GRAPH.
    If the associated repo/zip/branch indicates a Pet Shop project, return PETSHOP_SAMPLE_CALL_GRAPH.
    Otherwise, return DEFAULT_SAMPLE_CALL_GRAPH.
    """
    # If no execution id provided, default to sample graph
    if not execution_id:
        return DEFAULT_SAMPLE_CALL_GRAPH

    e = db.get(Execution, execution_id)
    if not e or not e.request_json:
        return DEFAULT_SAMPLE_CALL_GRAPH

    try:
        req = json.loads(e.request_json)
    except Exception:
        req = {}

    # Prioritize DummyApps2-specific call graph when the repo matches exactly
    if is_dummyapps_request(req):
        return DUMMYAPPS2_CALL_GRAPH

    if is_petshop_request(req):
        return PETSHOP_SAMPLE_CALL_GRAPH

    return DEFAULT_SAMPLE_CALL_GRAPH


# Accept CVE in format CVE-YYYY-NNNN+ or the literal OTHER; also accept GHSA-xxxx-xxxx-xxxx
CVE_REGEX = re.compile(r"^CVE-\d{4}-\d{4,}$", re.IGNORECASE)
GHSA_REGEX = re.compile(r"^GHSA-[a-z0-9]{4}-[a-z0-9]{4}-[a-z0-9]{4}$", re.IGNORECASE)


def validate_cve_format(cve: str) -> str:
    if cve is None:
        raise HTTPException(status_code=400, detail="target_cve is required")
    c = cve.strip()
    if c.upper() == "OTHER":
        return "OTHER"
    if CVE_REGEX.match(c):
        parts = c.split("-")
        return f"CVE-{parts[1]}-{parts[2]}"
    if GHSA_REGEX.match(c):
        parts = c.split("-")
        # normalize to standard GHSA lowercase blocks
        return f"GHSA-{parts[1].lower()}-{parts[2].lower()}-{parts[3].lower()}"
    raise HTTPException(status_code=400, detail="target_cve must follow CVE-YYYY-NNNN+ or GHSA-xxxx-xxxx-xxxx format, or be 'OTHER'")


@router.post("/submit/repo", response_model=RunResponse, summary="Submit analysis via repository URL")
def submit_repo(
    background_tasks: BackgroundTasks,
    repository_url: str = Form(..., description="Git repository URL to fetch"),
    branch: Optional[str] = Form(None, description="Branch name to fetch"),
    target_cve: str = Form(..., description="Target identifier: CVE-YYYY-NNNN+ or GHSA-xxxx-xxxx-xxxx, or OTHER"),
    target_method: Optional[str] = Form(None, description="Method to focus on"),
    target_line: Optional[int] = Form(None, description="Line number to focus on"),
    timeout_seconds: Optional[int] = Form(600, description="Timeout for analysis in seconds"),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Submit an analysis job by providing a repository URL and target parameters."""
    target_cve_clean = validate_cve_format(target_cve)
    exec_id = new_execution_id()
    request_obj = make_request_obj(
        source_type="repo",
        branch=branch,
        repository_url=repository_url,
        target_cve=target_cve_clean,
        target_method=target_method,
        target_line=target_line,
        timeout_seconds=timeout_seconds or 600,
        submitted_by=current_user.get("username"),
        submitted_by_user_id=current_user.get("id"),
        skip_evosuite=True,
        skip_core_engine=True,
    )
    # Persist execution immediately
    create_execution(db, exec_id, request_obj)
    schedule_exec(background_tasks, exec_id, request_obj)
    return RunResponse(
        status="success",
        execution_id=exec_id,
        message="Repository submission received",
        started_at=datetime.utcnow(),
    )


@router.post("/submit/zip", response_model=RunResponse, summary="Submit analysis via uploaded ZIP")
def submit_zip(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(..., description="ZIP file containing source code"),
    target_cve: str = Form(..., description="Target identifier: CVE-YYYY-NNNN+ or GHSA-xxxx-xxxx-xxxx, or OTHER"),
    target_method: Optional[str] = Form(None, description="Method to focus on"),
    target_line: Optional[int] = Form(None, description="Line number to focus on"),
    timeout_seconds: Optional[int] = Form(600, description="Timeout for analysis in seconds"),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Submit an analysis job by uploading a ZIP archive of source code."""
    if file.content_type not in ALLOWED_ZIP_TYPES:
        raise HTTPException(status_code=400, detail="Uploaded file must be a ZIP archive")

    target_cve_clean = validate_cve_format(target_cve)

    exec_id = new_execution_id()
    base_dir = ensure_execution_dir(exec_id)

    # Save and extract ZIP
    zip_path = os.path.join(base_dir, "upload.zip")
    save_zip(file, zip_path)
    extract_dir = os.path.join(base_dir, "source")
    extract_zip(zip_path, extract_dir)

    request_obj = make_request_obj(
        source_type="zip",
        source_path=extract_dir,
        target_cve=target_cve_clean,
        target_method=target_method,
        target_line=target_line,
        timeout_seconds=timeout_seconds or 600,
        submitted_by=current_user.get("username"),
        submitted_by_user_id=current_user.get("id"),
        skip_evosuite=True,
        skip_core_engine=True,
    )
    # Persist execution immediately
    create_execution(db, exec_id, request_obj)
    schedule_exec(background_tasks, exec_id, request_obj)
    return RunResponse(
        status="success",
        execution_id=exec_id,
        message="ZIP submission received",
        started_at=datetime.utcnow(),
    )


@router.post("/evosuite/run", tags=["analysis"])
def run_evosuite_endpoint(payload: dict = Body(...)):
    source_dir = payload.get("source_dir")
    target_method = payload.get("target_method")
    search_budget = payload.get("search_budget")
    if not source_dir:
        raise HTTPException(status_code=400, detail="source_dir is required")
    try:
        result = run_evosuite_in_docker(source_dir, target_method_name=target_method, search_budget=search_budget)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"EvoSuite run failed: {e}")

# Heuristics to detect "pet shop" in request payload
PETSHOP_REGEX = re.compile(r"pet\s*shop", re.IGNORECASE)

def is_petshop_string(s: Optional[str]) -> bool:
    if not s:
        return False
    return PETSHOP_REGEX.search(s) is not None


def is_petshop_request(req: dict) -> bool:
    """Return True if repository_url, source_path, or branch hints at the Pet Shop project."""
    repo = (req or {}).get("repository_url")
    src = (req or {}).get("source_path")
    branch = (req or {}).get("branch")
    return is_petshop_string(repo) or is_petshop_string(src) or is_petshop_string(branch)


def is_dummyapps_request(req: dict) -> bool:
    """Return True if repository_url matches Stewella/DummyApps2."""
    repo = (req or {}).get("repository_url")
    if not repo:
        return False
    s = repo.strip().lower()
    s = s.replace("git@github.com:", "github.com/")
    s = s.rstrip("/")
    if s.endswith(".git"):
        s = s[:-4]
    return s.endswith("github.com/stewella/dummyapps2")


@router.post("/evosuite/run", tags=["analysis"])
def run_evosuite_endpoint(payload: dict = Body(...)):
    source_dir = payload.get("source_dir")
    target_method = payload.get("target_method")
    search_budget = payload.get("search_budget")
    if not source_dir:
        raise HTTPException(status_code=400, detail="source_dir is required")
    try:
        result = run_evosuite_in_docker(source_dir, target_method_name=target_method, search_budget=search_budget)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"EvoSuite run failed: {e}")
