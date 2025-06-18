-- CreateTable
CREATE TABLE "SalesAgent" (
    "id" SERIAL NOT NULL,
    "name" TEXT NOT NULL,
    "phone_number" TEXT NOT NULL,

    CONSTRAINT "SalesAgent_pkey" PRIMARY KEY ("id")
);
